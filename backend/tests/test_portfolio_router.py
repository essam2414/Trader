"""Tests for the /api/portfolio routes (current portfolio and history)."""
from unittest.mock import MagicMock

from app.dependencies import get_trading212_client
from app.main import app
from app.models import PortfolioSnapshot

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
    """The endpoint should return the account summary and positions from the Trading212 client, including each position's instrument currency."""
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
