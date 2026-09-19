"""Tests for the snapshot service that persists portfolio totals to the database."""
from unittest.mock import MagicMock

from app.models import PortfolioSnapshot
from app.services.snapshot import take_snapshot


def test_take_snapshot_persists_totals_from_the_client(db_session):
    """take_snapshot should fetch the account summary from the client and store it as a PortfolioSnapshot row."""
    fake_client = MagicMock()
    fake_client.get_account_summary.return_value = {
        "currency": "USD",
        "totalValue": 10250.50,
        "investments": {"unrealizedProfitLoss": 750.50},
    }

    snapshot = take_snapshot(db_session, fake_client)

    assert snapshot.id is not None
    stored = db_session.query(PortfolioSnapshot).all()
    assert len(stored) == 1
    assert stored[0].total_value == 10250.50
    assert stored[0].unrealized_profit_loss == 750.50
    assert stored[0].currency == "USD"
