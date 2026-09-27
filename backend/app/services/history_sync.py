"""History sync service.

Pulls Trading212's order-fill and dividend history into the local
`order_fills` / `dividends` tables. A new database is fully backfilled once;
subsequent jobs inspect only the newest rate-limit-safe window and upsert by
id, skipping rows already stored.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from ..fx import HISTORICAL_RATE_TIMEOUT_SECONDS, get_historical_rate
from ..models import Dividend, HistorySyncState, OrderFill
from ..trading212 import Trading212Client

HISTORY_PAGE_SIZE = 50
MAX_HISTORY_PAGES_PER_RUN = 3
ORDER_HISTORY_PAGES_PER_RUN = 2
HISTORY_SYNC_TIME_BUDGET_SECONDS = 35.0
NATIVE_PRICE_BACKFILL_SOURCE = "native_prices"


@dataclass(frozen=True)
class HistoryPageBatch:
    """The persisted progress made while reading one history source."""

    added: int
    pages_fetched: int
    next_cursor: int | None
    reached_existing_item: bool


def _extract_cursor(next_page_path: str | None) -> int | None:
    """Pull the `cursor` query param out of a Trading212 `nextPagePath`."""
    if not next_page_path:
        return None
    query = parse_qs(urlparse(next_page_path).query)
    values = query.get("cursor")
    return int(values[0]) if values else None


def sync_order_fills(
    session: Session, client: Trading212Client, target_currency: str, max_pages: int | None = None
) -> int:
    """Sync historical order fills; returns the number of new rows added.

    Only fills with type "TRADE" are stored — corporate-action fills
    (splits, stock dividends, spin-offs, etc.) are skipped since they'd
    corrupt FIFO trade reconstruction.

    Trading212 fills carry a `price` in the instrument's own listing unit,
    which isn't always what it looks like: GBX-quoted UK instruments report
    price in pence while their `walletImpact` settles in pounds, and some
    trades on foreign-currency instruments settle through that currency's
    own cash sub-wallet rather than the account's base currency. `netValue`
    is always the true amount of `walletImpact.currency` that moved, so
    every fill is normalized here to `target_currency`: monetary fields are
    converted using the historical FX rate on the fill's date (a no-op,
    1.0 rate when the fill's currency already matches), and `fill_price` is
    derived as `net_value / quantity` in that target currency rather than
    trusted from the raw `price` field. The raw price and its instrument
    currency are retained separately for display in trade history.
    """
    return _sync_order_fill_pages(
        session,
        client,
        target_currency,
        cursor=None,
        max_pages=max_pages,
        stop_when_existing=False,
        deadline=None,
    ).added


def _sync_order_fill_pages(
    session: Session,
    client: Trading212Client,
    target_currency: str,
    *,
    cursor: int | None,
    max_pages: int | None,
    stop_when_existing: bool,
    deadline: float | None,
) -> HistoryPageBatch:
    """Read a bounded run of order pages and commit each page's progress.

    When catching up, the first previously stored fill proves that all older
    pages were imported by an earlier completed run. The caller then clears
    the saved continuation cursor.
    """
    existing_fills = {row.id: row for row in session.query(OrderFill).all()}
    rate_cache: dict[tuple[str, str], float] = {}
    added = 0
    pages_fetched = 0
    reached_existing_item = False
    next_cursor = cursor
    while max_pages is None or pages_fetched < max_pages:
        if deadline is not None and time.monotonic() >= deadline:
            break
        page = client.get_historical_orders(cursor=cursor, limit=HISTORY_PAGE_SIZE)
        required_fx_rates = _required_fx_rates(page["items"], existing_fills, target_currency, rate_cache)
        if (
            deadline is not None
            and time.monotonic() + (len(required_fx_rates) * HISTORICAL_RATE_TIMEOUT_SECONDS) >= deadline
        ):
            break
        pages_fetched += 1
        page_has_existing_item = False
        for item in page["items"]:
            fill = item.get("fill")
            if fill is None:
                # Unfilled orders (cancelled, rejected, still pending, etc.)
                # have no "fill" object at all - nothing to record.
                continue
            if fill["type"] != "TRADE":
                continue
            fill_id = str(fill["id"])
            order = item["order"]
            wallet_impact = fill["walletImpact"]
            fill_currency = wallet_impact["currency"]
            source_price = fill["price"]
            source_currency = order["currency"]

            existing_fill = existing_fills.get(fill_id)
            if existing_fill is not None:
                page_has_existing_item = True
                # Older installations did not retain the native quote. A
                # one-time full refresh populates it without changing the
                # normalized values used for P/L calculations.
                if existing_fill.source_price is None or existing_fill.source_currency is None:
                    existing_fill.source_price = source_price
                    existing_fill.source_currency = source_currency
                continue
            filled_at = datetime.fromisoformat(fill["filledAt"].replace("Z", "+00:00"))

            cache_key = (filled_at.date().isoformat(), fill_currency)
            if cache_key not in rate_cache:
                rate_cache[cache_key] = get_historical_rate(cache_key[0], fill_currency, target_currency)
            rate = rate_cache[cache_key]

            quantity = abs(fill["quantity"])
            net_value = wallet_impact["netValue"] * rate
            fees = sum(tax["quantity"] for tax in wallet_impact.get("taxes", [])) * rate
            realised_profit_loss = (wallet_impact.get("realisedProfitLoss") or 0.0) * rate
            fill_price = net_value / quantity if quantity else 0.0

            order_fill = OrderFill(
                id=fill_id,
                order_id=str(order["id"]),
                ticker=order["ticker"],
                side=order["side"],
                quantity=fill["quantity"],
                source_price=source_price,
                source_currency=source_currency,
                fill_price=fill_price,
                net_value=net_value,
                realised_profit_loss=realised_profit_loss,
                fees=fees,
                currency=target_currency,
                filled_at=filled_at,
            )
            session.add(order_fill)
            existing_fills[fill_id] = order_fill
            added += 1
        next_cursor = _extract_cursor(page.get("nextPagePath"))
        # A committed cursor makes an interrupted catch-up safe to resume:
        # previously inserted rows cannot make the next run stop early.
        session.commit()
        if page_has_existing_item:
            reached_existing_item = True
        if next_cursor is None or (stop_when_existing and page_has_existing_item):
            break
        cursor = next_cursor
    return HistoryPageBatch(added, pages_fetched, next_cursor, reached_existing_item)


def _required_fx_rates(
    items: list[dict],
    existing_fills: dict[str, OrderFill],
    target_currency: str,
    rate_cache: dict[tuple[str, str], float],
) -> set[tuple[str, str]]:
    """Return uncached FX lookups needed before this page can be committed."""
    required: set[tuple[str, str]] = set()
    for item in items:
        fill = item.get("fill")
        if fill is None or fill["type"] != "TRADE" or str(fill["id"]) in existing_fills:
            continue
        fill_currency = fill["walletImpact"]["currency"]
        if fill_currency == target_currency:
            continue
        filled_at = datetime.fromisoformat(fill["filledAt"].replace("Z", "+00:00"))
        cache_key = (filled_at.date().isoformat(), fill_currency)
        if cache_key not in rate_cache:
            required.add(cache_key)
    return required


def sync_dividends(session: Session, client: Trading212Client, max_pages: int | None = None) -> int:
    """Sync historical dividend payments; returns the number of new rows added.

    Unlike order fills, Trading212 reports dividend `amount` directly in the
    account's primary currency, so no FX normalization is needed here.
    """
    return _sync_dividend_pages(
        session,
        client,
        cursor=None,
        max_pages=max_pages,
        stop_when_existing=False,
        deadline=None,
    ).added


def _sync_dividend_pages(
    session: Session,
    client: Trading212Client,
    *,
    cursor: int | None,
    max_pages: int | None,
    stop_when_existing: bool,
    deadline: float | None,
) -> HistoryPageBatch:
    """Read a bounded run of dividend pages and commit each page's progress."""
    existing_ids = {row.id for row in session.query(Dividend.id).all()}
    added = 0
    pages_fetched = 0
    reached_existing_item = False
    next_cursor = cursor
    while max_pages is None or pages_fetched < max_pages:
        if deadline is not None and time.monotonic() >= deadline:
            break
        page = client.get_dividends(cursor=cursor, limit=HISTORY_PAGE_SIZE)
        pages_fetched += 1
        page_has_existing_item = False
        for item in page["items"]:
            dividend_id = item.get("reference") or (f"{item['ticker']}:{item['paidOn']}:{item['amount']}")
            if dividend_id in existing_ids:
                page_has_existing_item = True
                continue
            session.add(
                Dividend(
                    id=dividend_id,
                    ticker=item["ticker"],
                    amount=item["amount"],
                    currency=item["currency"],
                    type=item["type"],
                    paid_at=datetime.fromisoformat(item["paidOn"].replace("Z", "+00:00")),
                )
            )
            existing_ids.add(dividend_id)
            added += 1
        next_cursor = _extract_cursor(page.get("nextPagePath"))
        session.commit()
        if page_has_existing_item:
            reached_existing_item = True
        if next_cursor is None or (stop_when_existing and page_has_existing_item):
            break
        cursor = next_cursor
    return HistoryPageBatch(added, pages_fetched, next_cursor, reached_existing_item)


def sync_native_price_backfill(
    session: Session,
    client: Trading212Client,
    max_pages: int = MAX_HISTORY_PAGES_PER_RUN,
    deadline: float | None = None,
) -> bool:
    """Populate native quotes for historical fills in resumable rate-safe batches.

    Earlier app versions persisted only account-currency-normalized prices.
    A source-price refresh therefore needs every historical order page. Its
    cursor is committed after each page so a Trading212 rate limit cannot roll
    back prior progress or make the next scheduled run restart at page one.
    Returns ``True`` only once the complete backfill has finished.
    """
    if session.query(OrderFill.id).first() is None:
        # New databases get native quotes during their regular initial order
        # import, so there is nothing separate to backfill.
        return True

    state = session.get(HistorySyncState, NATIVE_PRICE_BACKFILL_SOURCE)
    if state is not None and state.continuation_cursor is None:
        return True

    if state is None:
        has_missing_native_price = (
            session.query(OrderFill)
            .filter((OrderFill.source_price.is_(None)) | (OrderFill.source_currency.is_(None)))
            .first()
            is not None
        )
        if not has_missing_native_price:
            session.add(HistorySyncState(source=NATIVE_PRICE_BACKFILL_SOURCE))
            session.commit()
            return True
        cursor: int | None = None
    else:
        cursor = int(state.continuation_cursor) if state.continuation_cursor is not None else None

    for _ in range(max_pages):
        if deadline is not None and time.monotonic() >= deadline:
            return False
        try:
            page = client.get_historical_orders(cursor=cursor, limit=HISTORY_PAGE_SIZE)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                # Earlier page updates have already been committed. Leave the
                # saved cursor intact and continue on the next scheduler run.
                return False
            raise
        for item in page["items"]:
            fill = item.get("fill")
            if fill is None or fill["type"] != "TRADE":
                continue
            stored_fill = session.get(OrderFill, str(fill["id"]))
            if stored_fill is not None and (
                stored_fill.source_price is None or stored_fill.source_currency is None
            ):
                stored_fill.source_price = fill["price"]
                stored_fill.source_currency = item["order"]["currency"]

        next_cursor = _extract_cursor(page.get("nextPagePath"))
        if state is None:
            state = HistorySyncState(source=NATIVE_PRICE_BACKFILL_SOURCE)
            session.add(state)
        state.continuation_cursor = str(next_cursor) if next_cursor is not None else None
        # Persist every page before the next request, which may be throttled.
        session.commit()

        if next_cursor is None:
            return True
        cursor = next_cursor

    return False


def _history_state(session: Session, source: str) -> HistorySyncState:
    state = session.get(HistorySyncState, source)
    if state is None:
        state = HistorySyncState(source=source)
        session.add(state)
    return state


def _save_page_batch(state: HistorySyncState, batch: HistoryPageBatch) -> None:
    if batch.pages_fetched == 0:
        return
    state.continuation_cursor = (
        None if batch.reached_existing_item or batch.next_cursor is None else str(batch.next_cursor)
    )
    if state.continuation_cursor is None:
        state.completed_at = datetime.now(timezone.utc)


def _state_cursor(state: HistorySyncState) -> int | None:
    return int(state.continuation_cursor) if state.continuation_cursor is not None else None


def sync_history(
    session: Session,
    client: Trading212Client,
    target_currency: str,
    *,
    deadline: float | None = None,
) -> None:
    """Sync history in resumable batches that finish within one scheduler tick.

    Each run fetches at most three pages across orders and dividends. A source
    with a saved cursor continues backwards on the next run until it reaches a
    previously stored item; then it returns to checking only the newest page.
    """
    if not sync_native_price_backfill(
        session,
        client,
        max_pages=MAX_HISTORY_PAGES_PER_RUN,
        deadline=deadline,
    ):
        # Reserve the order-history quota for the resumable native-price
        # backfill. The next scheduled run continues from its saved cursor.
        return

    pages_remaining = MAX_HISTORY_PAGES_PER_RUN
    order_state = _history_state(session, "orders")
    order_batch = _sync_order_fill_pages(
        session,
        client,
        target_currency,
        cursor=_state_cursor(order_state),
        max_pages=min(ORDER_HISTORY_PAGES_PER_RUN, pages_remaining),
        stop_when_existing=True,
        deadline=deadline,
    )
    _save_page_batch(order_state, order_batch)
    session.commit()
    pages_remaining -= order_batch.pages_fetched

    if pages_remaining == 0:
        return

    dividend_state = _history_state(session, "dividends")
    dividend_batch = _sync_dividend_pages(
        session,
        client,
        cursor=_state_cursor(dividend_state),
        max_pages=pages_remaining,
        stop_when_existing=True,
        deadline=deadline,
    )
    _save_page_batch(dividend_state, dividend_batch)
    session.commit()
