"""Snapshot service for Taking point-in-time portfolio snapshots.

Bridges the Trading212 API client and the database layer to periodically
capture and persist the account's total value, unrealized P&L, and currency.
"""

from sqlalchemy.orm import Session

from ..models import PortfolioSnapshot
from ..trading212 import Trading212Client


def take_snapshot(session: Session, client: Trading212Client) -> PortfolioSnapshot:
    """Capture and persist a point-in-time snapshot of portfolio value.

    Calls the Trading212 API to fetch the current account summary, extracts
    the total value, unrealized profit/loss, and currency, creates a
    PortfolioSnapshot record, persists it to the database, and returns it.

    Args:
        session: SQLAlchemy database session for persistence
        client: Trading212Client instance to fetch account data

    Returns:
        The newly created and persisted PortfolioSnapshot instance
    """
    summary = client.get_account_summary()
    snapshot = PortfolioSnapshot(
        total_value=summary["totalValue"],
        unrealized_profit_loss=summary["investments"]["unrealizedProfitLoss"],
        currency=summary["currency"],
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot
