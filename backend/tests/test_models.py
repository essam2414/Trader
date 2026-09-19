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


def test_order_fill_persists_with_all_fields(db_session):
    """An OrderFill should persist every synced field from a Trading212 fill."""
    from datetime import datetime, timezone

    from app.models import OrderFill

    fill = OrderFill(
        id="101",
        order_id="1",
        ticker="AAPL_US_EQ",
        side="BUY",
        quantity=10.0,
        fill_price=100.0,
        net_value=1000.0,
        realised_profit_loss=0.0,
        fees=1.0,
        currency="USD",
        filled_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
    )

    db_session.add(fill)
    db_session.commit()
    db_session.refresh(fill)

    assert fill.id == "101"
    assert fill.side == "BUY"
    assert fill.fees == 1.0


def test_dividend_persists_with_all_fields(db_session):
    """A Dividend should persist every synced field from a Trading212 dividend payment."""
    from datetime import datetime, timezone

    from app.models import Dividend

    dividend = Dividend(
        id="div-ref-1",
        ticker="AAPL_US_EQ",
        amount=5.0,
        currency="USD",
        type="ORDINARY",
        paid_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    db_session.add(dividend)
    db_session.commit()
    db_session.refresh(dividend)

    assert dividend.id == "div-ref-1"
    assert dividend.amount == 5.0
