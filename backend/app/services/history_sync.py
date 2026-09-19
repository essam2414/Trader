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

from ..models import Dividend, OrderFill
from ..trading212 import Trading212Client


def _extract_cursor(next_page_path: str | None) -> int | None:
    """Pull the `cursor` query param out of a Trading212 `nextPagePath`."""
    if not next_page_path:
        return None
    query = parse_qs(urlparse(next_page_path).query)
    values = query.get("cursor")
    return int(values[0]) if values else None


def sync_order_fills(session: Session, client: Trading212Client) -> int:
    """Sync historical order fills; returns the number of new rows added.

    Only fills with type "TRADE" are stored — corporate-action fills
    (splits, stock dividends, spin-offs, etc.) are skipped since they'd
    corrupt FIFO trade reconstruction.
    """
    existing_ids = {row.id for row in session.query(OrderFill.id).all()}
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
            fees = sum(tax["quantity"] for tax in wallet_impact.get("taxes", []))
            session.add(
                OrderFill(
                    id=fill_id,
                    order_id=str(order["id"]),
                    ticker=order["ticker"],
                    side=order["side"],
                    quantity=fill["quantity"],
                    fill_price=fill["price"],
                    net_value=wallet_impact["netValue"],
                    realised_profit_loss=wallet_impact.get("realisedProfitLoss") or 0.0,
                    fees=fees,
                    currency=wallet_impact["currency"],
                    filled_at=datetime.fromisoformat(fill["filledAt"].replace("Z", "+00:00")),
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
    """Sync historical dividend payments; returns the number of new rows added."""
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


def sync_history(session: Session, client: Trading212Client) -> None:
    """Sync both order fills and dividends; invoked on a timer by the scheduler."""
    sync_order_fills(session, client)
    sync_dividends(session, client)
