"""History sync service.

Pulls Trading212's order-fill and dividend history into the local
`order_fills` / `dividends` tables. A new database is fully backfilled once;
subsequent jobs inspect only the newest rate-limit-safe window and upsert by
id, skipping rows already stored.
"""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from ..fx import get_historical_rate
from ..models import Dividend, HistorySyncState, OrderFill
from ..trading212 import Trading212Client

HISTORY_PAGE_SIZE = 50
MAX_RECENT_HISTORY_PAGES = 6


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
    trusted from the raw `price` field.
    """
    existing_ids = {row.id for row in session.query(OrderFill.id).all()}
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
            if fill_id in existing_ids:
                continue
            order = item["order"]
            wallet_impact = fill["walletImpact"]
            fill_currency = wallet_impact["currency"]
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

            session.add(
                OrderFill(
                    id=fill_id,
                    order_id=str(order["id"]),
                    ticker=order["ticker"],
                    side=order["side"],
                    quantity=fill["quantity"],
                    fill_price=fill_price,
                    net_value=net_value,
                    realised_profit_loss=realised_profit_loss,
                    fees=fees,
                    currency=target_currency,
                    filled_at=filled_at,
                )
            )
            existing_ids.add(fill_id)
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
