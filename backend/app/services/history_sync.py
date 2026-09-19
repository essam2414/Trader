"""History sync service.

Pulls Trading212's order-fill and dividend history into the local
`order_fills` / `dividends` tables. Each run walks every page of both
endpoints (page ordering isn't documented, so an early-stop-at-known-id
shortcut isn't safe) and upserts by id, skipping ids already stored. At
single-user, hundreds-of-fills scale this is a handful of API calls per run.
"""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from ..fx import get_historical_rate
from ..models import Dividend, OrderFill
from ..trading212 import Trading212Client


def _extract_cursor(next_page_path: str | None) -> int | None:
    """Pull the `cursor` query param out of a Trading212 `nextPagePath`."""
    if not next_page_path:
        return None
    query = parse_qs(urlparse(next_page_path).query)
    values = query.get("cursor")
    return int(values[0]) if values else None


def sync_order_fills(session: Session, client: Trading212Client, target_currency: str) -> int:
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
    while True:
        page = client.get_historical_orders(cursor=cursor)
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


def sync_dividends(session: Session, client: Trading212Client) -> int:
    """Sync historical dividend payments; returns the number of new rows added.

    Unlike order fills, Trading212 reports dividend `amount` directly in the
    account's primary currency, so no FX normalization is needed here.
    """
    existing_ids = {row.id for row in session.query(Dividend.id).all()}
    added = 0
    cursor: int | None = None
    while True:
        page = client.get_dividends(cursor=cursor)
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


def sync_history(session: Session, client: Trading212Client, target_currency: str) -> None:
    """Sync both order fills and dividends; invoked on a timer by the scheduler."""
    sync_order_fills(session, client, target_currency)
    sync_dividends(session, client)
