"""Watchlist route responses, including cached company logo delivery."""

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
