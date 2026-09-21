"""History sync service.

Pulls Trading212's order-fill and dividend history into the local
`order_fills` / `dividends` tables. A new database is fully backfilled once;
subsequent jobs inspect only the newest rate-limit-safe window and upsert by
id, skipping rows already stored.
"""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from ..fx import get_historical_rate
from ..models import Dividend, HistorySyncState, OrderFill
from ..trading212 import Trading212Client

HISTORY_PAGE_SIZE = 50
MAX_RECENT_HISTORY_PAGES = 6
NATIVE_PRICE_BACKFILL_PAGES = 5
NATIVE_PRICE_BACKFILL_SOURCE = "native_prices"


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
    existing_fills = {row.id: row for row in session.query(OrderFill).all()}
    rate_cache: dict[tuple[str, str], float] = {}
    added = 0
    cursor: int | None = None
    pages_fetched = 0
    while max_pages is None or pages_fetched < max_pages:
        page = client.get_historical_orders(cursor=cursor, limit=HISTORY_PAGE_SIZE)
        pages_fetched += 1
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
        cursor = _extract_cursor(page.get("nextPagePath"))
        if cursor is None:
            break
    session.commit()
    return added


def sync_dividends(session: Session, client: Trading212Client, max_pages: int | None = None) -> int:
    """Sync historical dividend payments; returns the number of new rows added.

    Unlike order fills, Trading212 reports dividend `amount` directly in the
    account's primary currency, so no FX normalization is needed here.
    """
    existing_ids = {row.id for row in session.query(Dividend.id).all()}
    added = 0
    cursor: int | None = None
    pages_fetched = 0
    while max_pages is None or pages_fetched < max_pages:
        page = client.get_dividends(cursor=cursor, limit=HISTORY_PAGE_SIZE)
        pages_fetched += 1
        for item in page["items"]:
            dividend_id = item.get("reference") or (f"{item['ticker']}:{item['paidOn']}:{item['amount']}")
            if dividend_id in existing_ids:
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
        cursor = _extract_cursor(page.get("nextPagePath"))
        if cursor is None:
            break
    session.commit()
    return added


def sync_native_price_backfill(
    session: Session, client: Trading212Client, max_pages: int = NATIVE_PRICE_BACKFILL_PAGES
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


def _initial_backfill_complete(
    session: Session, source: str, model: type[OrderFill] | type[Dividend]
) -> bool:
    if session.get(HistorySyncState, source) is not None:
        return True

    # Existing installations predate HistorySyncState. Their populated
    # history is already a completed backfill, so do not restart a multi-
    # minute full scan merely because the checkpoint table is new.
    if session.query(model.id).first() is None:
        return False

    _mark_initial_backfill_complete(session, source)
    return True


def _mark_initial_backfill_complete(session: Session, source: str) -> None:
    session.add(HistorySyncState(source=source))
    session.commit()


def sync_history(session: Session, client: Trading212Client, target_currency: str) -> None:
    """Sync history without exceeding Trading212's six-request-per-minute quota.

    New installations fully backfill each source once. Afterwards, each
    minute checks the six newest 50-item pages (300 events) and skips IDs
    that are already in the database. That window comfortably covers new
    events between successful minute runs while keeping each endpoint within
    its own documented request budget.
    """
    if not sync_native_price_backfill(session, client):
        # Reserve the order-history quota for the resumable native-price
        # backfill. The next scheduled run continues from its saved cursor.
        return

    orders_backfilled = _initial_backfill_complete(session, "orders", OrderFill)
    sync_order_fills(
        session,
        client,
        target_currency,
        max_pages=MAX_RECENT_HISTORY_PAGES if orders_backfilled else None,
    )
    if not orders_backfilled:
        _mark_initial_backfill_complete(session, "orders")

    dividends_backfilled = _initial_backfill_complete(session, "dividends", Dividend)
    sync_dividends(
        session,
        client,
        max_pages=MAX_RECENT_HISTORY_PAGES if dividends_backfilled else None,
    )
    if not dividends_backfilled:
        _mark_initial_backfill_complete(session, "dividends")
