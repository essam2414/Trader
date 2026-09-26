"""Batch purchase levels for the Trends chart grid."""

from app.config import settings
from app.dependencies import get_trading212_client
from app.main import app
from app.models import WatchlistEntry


def test_watchlist_positions_fetches_trading212_once_for_all_charts(client, db_session):
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="asset-msft", symbol="MSFT", name="Microsoft", exchange="NASDAQ"),
        ]
    )
    db_session.commit()

    class FakeTrading212:
        calls = 0

        def get_positions(self):
            self.calls += 1
            return [{"instrument": {"ticker": "AAPL_US_EQ", "currency": "USD"}, "averagePricePaid": 150.25}]

    fake = FakeTrading212()
    app.dependency_overrides[get_trading212_client] = lambda: fake
    response = client.get(
        "/api/watchlist/positions",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "asset-aapl": {"purchasePrice": 150.25, "purchasePriceCurrency": "USD"},
        "asset-msft": {"purchasePrice": None, "purchasePriceCurrency": None},
    }
    assert fake.calls == 1
