"""Watchlist route responses, including cached company logo delivery."""

from app.alpaca_market_data import AlpacaAsset
from app.config import settings
from app.dependencies import get_alpaca_market_data_client
from app.main import app
from app.models import WatchlistEntry


def test_watchlist_logo_returns_the_cached_image(client, db_session):
    db_session.add(
        WatchlistEntry(
            alpaca_asset_id="asset-aapl",
            symbol="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            logo_data=b"webp-logo",
            logo_content_type="image/webp",
            logo_provider="eulerpool",
        )
    )
    db_session.commit()
    app.dependency_overrides[get_alpaca_market_data_client] = lambda: object()

    response = client.get(
        "/api/watchlist/asset-aapl/logo",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.content == b"webp-logo"
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=604800, immutable"


def test_adding_stock_makes_its_logo_available_immediately(client):
    class LogoClient:
        feed = "iex"

        def get_asset(self, asset_id):
            return AlpacaAsset("asset-aapl", "AAPL", "Apple Inc.", "NASDAQ")

        def get_company_logo(self, symbol):
            assert symbol == "AAPL"
            return b"apple-logo", "image/png"

    app.dependency_overrides[get_alpaca_market_data_client] = LogoClient
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}

    added = client.post("/api/watchlist", json={"assetId": "asset-aapl"}, headers=headers)
    logo = client.get(added.json()["logoUrl"], headers=headers)

    assert added.status_code == 201
    assert logo.status_code == 200
    assert logo.content == b"apple-logo"
    assert logo.headers["content-type"] == "image/png"


def test_svg_logo_response_is_sandboxed(client, db_session):
    db_session.add(
        WatchlistEntry(
            alpaca_asset_id="asset-aapl",
            symbol="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            logo_data=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            logo_content_type="image/svg+xml",
        )
    )
    db_session.commit()
    app.dependency_overrides[get_alpaca_market_data_client] = lambda: object()

    response = client.get(
        "/api/watchlist/asset-aapl/logo",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["content-security-policy"] == (
        "sandbox; default-src 'none'; style-src 'unsafe-inline'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
