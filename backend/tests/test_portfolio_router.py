"""Tests for the /api/portfolio routes (current portfolio and history)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.dependencies import get_trading212_client
from app.main import app
from app.models import OrderFill, PortfolioSnapshot

FAKE_SUMMARY = {
    "id": 1,
    "currency": "USD",
    "totalValue": 10250.50,
    "cash": {"availableToTrade": 500.0, "inPies": 0.0, "reservedForOrders": 0.0},
    "investments": {
        "currentValue": 9750.50,
        "totalCost": 9000.0,
        "unrealizedProfitLoss": 750.50,
        "realizedProfitLoss": 120.0,
    },
}
FAKE_POSITIONS = [
    {
        "instrument": {"ticker": "NVDA_US_EQ", "name": "NVIDIA Corp", "isin": "US1", "currency": "USD"},
        "quantity": 10.0,
        "averagePricePaid": 120.5,
        "currentPrice": 135.2,
        "walletImpact": {
            "currency": "USD",
            "currentValue": 1352.0,
            "fxImpact": 0.0,
            "totalCost": 1205.0,
            "unrealizedProfitLoss": 147.0,
        },
    }
]
AUTH_HEADER = {"Authorization": "Bearer test-dashboard-key"}


def test_get_current_portfolio_returns_account_and_positions(client):
    """Returns the account summary and positions, including each position's currency."""
    fake_client = MagicMock()
    fake_client.get_account_summary.return_value = FAKE_SUMMARY
    fake_client.get_positions.return_value = FAKE_POSITIONS
    app.dependency_overrides[get_trading212_client] = lambda: fake_client

    response = client.get("/api/portfolio/current", headers=AUTH_HEADER)

    del app.dependency_overrides[get_trading212_client]
    assert response.status_code == 200
    body = response.json()
    assert body["account"]["totalValue"] == 10250.50
    assert body["positions"][0]["ticker"] == "NVDA_US_EQ"
    assert body["positions"][0]["currency"] == "USD"
    assert body["positions"][0]["unrealizedProfitLoss"] == 147.0


def test_get_current_portfolio_reuses_a_recent_live_response(client):
    """A second dashboard render within Trading212's five-second window is immediate."""
    fake_client = MagicMock()
    fake_client.get_account_summary.return_value = FAKE_SUMMARY
    fake_client.get_positions.return_value = FAKE_POSITIONS
    app.dependency_overrides[get_trading212_client] = lambda: fake_client

    first = client.get("/api/portfolio/current", headers=AUTH_HEADER)
    second = client.get("/api/portfolio/current", headers=AUTH_HEADER)

    del app.dependency_overrides[get_trading212_client]
    assert first.status_code == 200
    assert second.status_code == 200
    fake_client.get_account_summary.assert_called_once()
    fake_client.get_positions.assert_called_once()


def test_get_current_portfolio_returns_502_when_trading212_unreachable(client):
    """If the Trading212 client fails (bad credentials, network error), the endpoint
    should translate that into a 502 with a clear message, not leak a raw 500."""
    fake_client = MagicMock()
    fake_client.get_account_summary.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized",
        request=httpx.Request("GET", "https://live.trading212.com/api/v0/equity/account/summary"),
        response=httpx.Response(401),
    )
    app.dependency_overrides[get_trading212_client] = lambda: fake_client

    response = client.get("/api/portfolio/current", headers=AUTH_HEADER)

    del app.dependency_overrides[get_trading212_client]
    assert response.status_code == 502
    assert "Trading212" in response.json()["detail"]


def test_get_current_portfolio_requires_auth(client):
    """The endpoint should reject requests without a valid bearer token."""
    response = client.get("/api/portfolio/current")

    assert response.status_code == 401


def test_get_portfolio_history_returns_stored_snapshots(client, db_session):
    """The endpoint should return previously stored portfolio snapshots."""
    db_session.add(PortfolioSnapshot(total_value=100.0, unrealized_profit_loss=5.0, currency="USD"))
    db_session.commit()

    response = client.get("/api/portfolio/history", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["totalValue"] == 100.0


def test_get_portfolio_metrics_returns_computed_metrics_from_synced_history(client, db_session):
    """The endpoint should compute metrics purely from synced DB history - no
    Trading212 call needed, so it can't fail or contend with /portfolio/current
    for Trading212's request budget when both are fetched concurrently on
    every dashboard load."""
    db_session.add_all(
        [
            OrderFill(
                id="1",
                order_id="1",
                ticker="AAPL_US_EQ",
                side="BUY",
                quantity=10.0,
                fill_price=100.0,
                net_value=1000.0,
                realised_profit_loss=0.0,
                fees=0.0,
                currency="USD",
                filled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            OrderFill(
                id="2",
                order_id="2",
                ticker="AAPL_US_EQ",
                side="SELL",
                quantity=10.0,
                fill_price=110.0,
                net_value=1100.0,
                realised_profit_loss=100.0,
                fees=0.0,
                currency="USD",
                filled_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/portfolio/metrics", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["closedTradeCount"] == 1
    assert body["realizedPnl"] == pytest.approx(100.0)
    assert body["winRate"] == pytest.approx(1.0)
    assert "cashDrag" not in body
    assert len(body["trades"]) == 1
    trade = body["trades"][0]
    assert trade["ticker"] == "AAPL_US_EQ"
    assert trade["quantity"] == 10.0
    assert trade["entryPrice"] == 100.0
    assert trade["exitPrice"] == 110.0
    assert trade["pnl"] == pytest.approx(100.0)
    assert trade["holdingPeriodHours"] == pytest.approx(96.0)


def test_get_portfolio_metrics_requires_auth(client):
    response = client.get("/api/portfolio/metrics")

    assert response.status_code == 401
