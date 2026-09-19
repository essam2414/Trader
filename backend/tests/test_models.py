"""Tests for the PortfolioSnapshot ORM model."""
from app.models import PortfolioSnapshot


def test_portfolio_snapshot_persists_with_defaults(db_session):
    """A PortfolioSnapshot should persist and get default id/taken_at values on commit."""
    snapshot = PortfolioSnapshot(total_value=10250.50, unrealized_profit_loss=750.50, currency="USD")

    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)

    assert snapshot.id is not None
    assert snapshot.taken_at is not None
    assert snapshot.total_value == 10250.50
    assert snapshot.currency == "USD"
