"""Tests for the history sync service that persists Trading212 order/dividend history."""

from unittest.mock import MagicMock

from app.models import Dividend, OrderFill
from app.services.history_sync import sync_dividends, sync_history, sync_order_fills

ORDER_PAGE_1 = {
    "items": [
        {
            "order": {"id": 1, "ticker": "AAPL_US_EQ", "side": "BUY", "currency": "USD"},
            "fill": {
                "id": 101,
                "filledAt": "2026-01-01T10:00:00Z",
                "quantity": 10.0,
                "price": 100.0,
                "type": "TRADE",
                "walletImpact": {
                    "currency": "USD",
                    "netValue": 1000.0,
                    "realisedProfitLoss": 0.0,
                    "taxes": [{"name": "COMMISSION_TURNOVER", "quantity": 1.0}],
                },
            },
        },
        {
            "order": {"id": 2, "ticker": "AAPL_US_EQ", "side": "SELL", "currency": "USD"},
            "fill": {
                "id": 102,
                "filledAt": "2026-01-05T10:00:00Z",
                "quantity": 10.0,
                "price": 110.0,
                "type": "STOCK_SPLIT",
                "walletImpact": {
                    "currency": "USD",
                    "netValue": 1100.0,
                    "realisedProfitLoss": 100.0,
                    "taxes": [],
                },
            },
        },
    ],
    "nextPagePath": "/api/v0/equity/history/orders?cursor=2&limit=50",
}
ORDER_PAGE_2 = {
    "items": [
        {
            "order": {"id": 3, "ticker": "MSFT_US_EQ", "side": "SELL", "currency": "USD"},
            "fill": {
                "id": 103,
                "filledAt": "2026-01-11T12:00:00Z",
                "quantity": 2.0,
                "price": 205.0,
                "type": "TRADE",
                "walletImpact": {
                    "currency": "USD",
                    "netValue": 410.0,
                    "realisedProfitLoss": 10.0,
                    "taxes": [],
                },
            },
        },
        {
            # A cancelled/unfilled order has no "fill" object at all - real
            # Trading212 responses include these alongside filled orders.
            "order": {
                "id": 4,
                "ticker": "TSLA_US_EQ",
                "side": "BUY",
                "currency": "USD",
                "status": "CANCELLED",
            },
        },
    ],
    "nextPagePath": None,
}
DIVIDEND_PAGE = {
    "items": [
        {
            "ticker": "AAPL_US_EQ",
            "amount": 5.0,
            "currency": "USD",
            "type": "ORDINARY",
            "paidOn": "2026-01-15T00:00:00Z",
            "reference": "div-ref-1",
        },
        {
            "ticker": "MSFT_US_EQ",
            "amount": 2.0,
            "currency": "USD",
            "type": "ORDINARY",
            "paidOn": "2026-01-20T00:00:00Z",
        },
    ],
    "nextPagePath": None,
}


def test_sync_order_fills_paginates_and_filters_non_trade_fills(db_session):
    """sync_order_fills should walk every page and only store fills with type TRADE.

    fill 101 (BUY, TRADE) and fill 103 (SELL, TRADE) are stored; 102 is
    STOCK_SPLIT (a corporate action, not a trade) and order 4 has no "fill"
    at all (a cancelled order) - both are skipped without error.
    """
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    added = sync_order_fills(db_session, fake_client)

    assert added == 2
    stored_ids = {row.id for row in db_session.query(OrderFill).all()}
    assert stored_ids == {"101", "103"}
    assert fake_client.get_historical_orders.call_count == 2
    fake_client.get_historical_orders.assert_any_call(cursor=None)
    fake_client.get_historical_orders.assert_any_call(cursor=2)


def test_sync_order_fills_sums_taxes_into_fees(db_session):
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    sync_order_fills(db_session, fake_client)

    stored = db_session.query(OrderFill).filter_by(id="101").one()
    assert stored.fees == 1.0
    assert stored.side == "BUY"
    assert stored.ticker == "AAPL_US_EQ"


def test_sync_order_fills_is_idempotent(db_session):
    """Running the sync twice should not create duplicate rows."""
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [
        ORDER_PAGE_1,
        ORDER_PAGE_2,
        ORDER_PAGE_1,
        ORDER_PAGE_2,
    ]

    sync_order_fills(db_session, fake_client)
    second_added = sync_order_fills(db_session, fake_client)

    assert second_added == 0
    assert db_session.query(OrderFill).count() == 2


def test_sync_dividends_uses_reference_or_falls_back_to_composite_key(db_session):
    """A dividend with a `reference` uses it as the id; without one, falls back
    to a composite key of ticker/date/amount."""
    fake_client = MagicMock()
    fake_client.get_dividends.side_effect = [DIVIDEND_PAGE]

    added = sync_dividends(db_session, fake_client)

    assert added == 2
    stored_ids = {row.id for row in db_session.query(Dividend).all()}
    assert "div-ref-1" in stored_ids
    assert "MSFT_US_EQ:2026-01-20T00:00:00Z:2.0" in stored_ids


def test_sync_history_syncs_both_orders_and_dividends(db_session):
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]
    fake_client.get_dividends.side_effect = [DIVIDEND_PAGE]

    sync_history(db_session, fake_client)

    assert db_session.query(OrderFill).count() == 2
    assert db_session.query(Dividend).count() == 2
