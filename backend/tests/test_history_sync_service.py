"""Tests for the history sync service that persists Trading212 order/dividend history."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx

from app.models import Dividend, HistorySyncState, OrderFill
from app.services.history_sync import (
    NATIVE_PRICE_BACKFILL_SOURCE,
    sync_dividends,
    sync_history,
    sync_native_price_backfill,
    sync_order_fills,
)

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
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2, ORDER_PAGE_1, ORDER_PAGE_2]

    added = sync_order_fills(db_session, fake_client, target_currency="USD")

    assert added == 2
    stored_ids = {row.id for row in db_session.query(OrderFill).all()}
    assert stored_ids == {"101", "103"}
    assert fake_client.get_historical_orders.call_count == 2
    fake_client.get_historical_orders.assert_any_call(cursor=None, limit=50)
    fake_client.get_historical_orders.assert_any_call(cursor=2, limit=50)


def test_sync_order_fills_sums_taxes_into_fees(db_session):
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    sync_order_fills(db_session, fake_client, target_currency="USD")

    stored = db_session.query(OrderFill).filter_by(id="101").one()
    assert stored.fees == 1.0
    assert stored.side == "BUY"
    assert stored.ticker == "AAPL_US_EQ"


def test_sync_order_fills_derives_price_from_net_value_over_quantity(db_session):
    """fill_price should come from net_value/quantity, not the raw fill
    price - Trading212 quotes some instruments (e.g. GBX-denominated UK
    stocks) in a different unit than netValue is settled in, so the raw
    price field alone isn't reliable."""
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    sync_order_fills(db_session, fake_client, target_currency="USD")

    stored = db_session.query(OrderFill).filter_by(id="101").one()
    assert stored.fill_price == 100.0  # netValue 1000.0 / quantity 10.0, not the raw price=100.0 (same here)
    assert stored.source_price == 100.0
    assert stored.source_currency == "USD"
    stored_sell = db_session.query(OrderFill).filter_by(id="103").one()
    assert stored_sell.fill_price == 205.0  # netValue 410.0 / |quantity| 2.0


def test_sync_order_fills_is_idempotent(db_session):
    """Running the sync twice should not create duplicate rows."""
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [
        ORDER_PAGE_1,
        ORDER_PAGE_2,
        ORDER_PAGE_1,
        ORDER_PAGE_2,
    ]

    sync_order_fills(db_session, fake_client, target_currency="USD")
    second_added = sync_order_fills(db_session, fake_client, target_currency="USD")

    assert second_added == 0
    assert db_session.query(OrderFill).count() == 2


def test_sync_order_fills_caps_minute_sync_at_six_fifty_item_pages(db_session):
    """A recurring sync must stay inside Trading212's six-requests-per-minute limit."""
    fake_client = MagicMock()
    pages = [
        {"items": [], "nextPagePath": f"/api/v0/equity/history/orders?cursor={page}&limit=50"}
        for page in range(1, 7)
    ]
    fake_client.get_historical_orders.side_effect = pages

    sync_order_fills(db_session, fake_client, target_currency="USD", max_pages=6)

    assert fake_client.get_historical_orders.call_count == 6
    assert fake_client.get_historical_orders.call_args_list[0].kwargs == {"cursor": None, "limit": 50}
    assert fake_client.get_historical_orders.call_args_list[-1].kwargs == {"cursor": 5, "limit": 50}


@patch("app.services.history_sync.get_historical_rate")
def test_sync_order_fills_converts_non_target_currency_fills(mock_get_rate, db_session):
    """A fill that settled in a currency other than target_currency should
    have its monetary fields converted using that date's historical rate,
    and be stored under target_currency."""
    mock_get_rate.return_value = 0.8
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    sync_order_fills(db_session, fake_client, target_currency="GBP")

    stored = db_session.query(OrderFill).filter_by(id="101").one()
    assert stored.currency == "GBP"
    assert stored.net_value == 800.0  # 1000.0 * 0.8
    assert stored.fees == 0.8  # 1.0 * 0.8
    assert stored.fill_price == 80.0  # converted net_value 800.0 / quantity 10.0
    assert stored.source_price == 100.0
    assert stored.source_currency == "USD"
    mock_get_rate.assert_any_call("2026-01-01", "USD", "GBP")


@patch("app.services.history_sync.get_historical_rate")
def test_sync_order_fills_caches_fx_rate_per_date_and_currency(mock_get_rate, db_session):
    """Two fills sharing the same (date, currency) pair should only trigger
    one rate lookup, not one per fill."""
    mock_get_rate.return_value = 0.8
    same_day_page = {
        "items": [
            {
                "order": {"id": 10, "ticker": "AAPL_US_EQ", "side": "BUY", "currency": "USD"},
                "fill": {
                    "id": 201,
                    "filledAt": "2026-03-01T09:00:00Z",
                    "quantity": 5.0,
                    "price": 50.0,
                    "type": "TRADE",
                    "walletImpact": {
                        "currency": "USD",
                        "netValue": 250.0,
                        "realisedProfitLoss": 0.0,
                        "taxes": [],
                    },
                },
            },
            {
                "order": {"id": 11, "ticker": "AAPL_US_EQ", "side": "SELL", "currency": "USD"},
                "fill": {
                    "id": 202,
                    "filledAt": "2026-03-01T15:00:00Z",
                    "quantity": -5.0,
                    "price": 55.0,
                    "type": "TRADE",
                    "walletImpact": {
                        "currency": "USD",
                        "netValue": 275.0,
                        "realisedProfitLoss": 25.0,
                        "taxes": [],
                    },
                },
            },
        ],
        "nextPagePath": None,
    }
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [same_day_page]

    sync_order_fills(db_session, fake_client, target_currency="GBP")

    assert db_session.query(OrderFill).count() == 2
    assert mock_get_rate.call_count == 1


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

    sync_history(db_session, fake_client, target_currency="USD")

    assert db_session.query(OrderFill).count() == 2
    assert db_session.query(Dividend).count() == 2
    assert {state.source for state in db_session.query(HistorySyncState).all()} == {"orders", "dividends"}


@patch("app.services.history_sync.get_historical_rate", return_value=0.8)
def test_sync_history_backfills_native_prices_for_existing_fills(mock_get_rate, db_session):
    """An upgraded installation refreshes its prior fills' native quotes once."""
    db_session.add(
        OrderFill(
            id="101",
            order_id="1",
            ticker="AAPL_US_EQ",
            side="BUY",
            quantity=10.0,
            fill_price=80.0,
            net_value=800.0,
            realised_profit_loss=0.0,
            fees=0.0,
            currency="GBP",
            filled_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        )
    )
    db_session.add(HistorySyncState(source="orders"))
    db_session.commit()

    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2, ORDER_PAGE_1, ORDER_PAGE_2]
    fake_client.get_dividends.side_effect = [DIVIDEND_PAGE]

    sync_history(db_session, fake_client, target_currency="GBP")

    stored = db_session.get(OrderFill, "101")
    assert stored is not None
    assert stored.source_price == 100.0
    assert stored.source_currency == "USD"


def test_native_price_backfill_resumes_from_its_saved_cursor(db_session):
    """A rate-safe batch continues from its last committed history page."""
    db_session.add(
        OrderFill(
            id="101",
            order_id="1",
            ticker="AAPL_US_EQ",
            side="BUY",
            quantity=10.0,
            fill_price=80.0,
            net_value=800.0,
            realised_profit_loss=0.0,
            fees=0.0,
            currency="GBP",
            filled_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    assert not sync_native_price_backfill(db_session, fake_client, max_pages=1)
    stored = db_session.get(OrderFill, "101")
    state = db_session.get(HistorySyncState, NATIVE_PRICE_BACKFILL_SOURCE)
    assert stored is not None
    assert stored.source_price == 100.0
    assert stored.source_currency == "USD"
    assert state is not None
    assert state.continuation_cursor == "2"

    assert sync_native_price_backfill(db_session, fake_client, max_pages=1)
    assert state.continuation_cursor is None
    assert fake_client.get_historical_orders.call_args_list[0].kwargs == {"cursor": None, "limit": 50}
    assert fake_client.get_historical_orders.call_args_list[1].kwargs == {"cursor": 2, "limit": 50}


def test_native_price_backfill_preserves_progress_when_rate_limited(db_session):
    db_session.add(
        OrderFill(
            id="101",
            order_id="1",
            ticker="AAPL_US_EQ",
            side="BUY",
            quantity=10.0,
            fill_price=80.0,
            net_value=800.0,
            realised_profit_loss=0.0,
            fees=0.0,
            currency="GBP",
            filled_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    rate_limit_error = httpx.HTTPStatusError(
        "429 Too Many Requests",
        request=httpx.Request("GET", "https://live.trading212.com/api/v0/equity/history/orders"),
        response=httpx.Response(429),
    )
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, rate_limit_error]

    assert not sync_native_price_backfill(db_session, fake_client, max_pages=2)
    stored = db_session.get(OrderFill, "101")
    state = db_session.get(HistorySyncState, NATIVE_PRICE_BACKFILL_SOURCE)
    assert stored is not None
    assert stored.source_price == 100.0
    assert state is not None
    assert state.continuation_cursor == "2"


def test_sync_history_uses_six_recent_pages_after_initial_backfill(db_session):
    db_session.add_all([HistorySyncState(source="orders"), HistorySyncState(source="dividends")])
    db_session.commit()
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [
        {"items": [], "nextPagePath": f"/api/v0/equity/history/orders?cursor={page}&limit=50"}
        for page in range(1, 7)
    ]
    fake_client.get_dividends.side_effect = [
        {"items": [], "nextPagePath": f"/api/v0/equity/history/dividends?cursor={page}&limit=50"}
        for page in range(1, 7)
    ]

    sync_history(db_session, fake_client, target_currency="USD")

    assert fake_client.get_historical_orders.call_count == 6
    assert fake_client.get_dividends.call_count == 6


def test_sync_history_marks_existing_history_as_backfilled(db_session):
    """Adding checkpoints must not restart a full scan of an existing database."""
    initial_client = MagicMock()
    initial_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]
    sync_order_fills(db_session, initial_client, target_currency="USD")

    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [
        {"items": [], "nextPagePath": f"/api/v0/equity/history/orders?cursor={page}&limit=50"}
        for page in range(1, 7)
    ]
    fake_client.get_dividends.return_value = {"items": [], "nextPagePath": None}

    sync_history(db_session, fake_client, target_currency="USD")

    assert fake_client.get_historical_orders.call_count == 6
    assert {state.source for state in db_session.query(HistorySyncState).all()} == {
        "orders",
        "dividends",
        NATIVE_PRICE_BACKFILL_SOURCE,
    }
