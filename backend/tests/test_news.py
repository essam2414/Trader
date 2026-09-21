"""Watchlist-only Alpaca news behaviour."""

from datetime import datetime

from app.alpaca_market_data import AlpacaMarketDataClient, NewsArticle
from app.config import settings
from app.dependencies import get_alpaca_market_data_client
from app.main import app
from app.models import WatchlistEntry


def test_news_client_filters_duplicate_ids_and_orders_last_updated_first(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    requested = {}

    def fake_request(_base_url, path, params):
        requested.update(path=path, params=params)
        return {
            "news": [
                article(2, "Later", "2026-09-21T11:00:00Z", "2026-09-21T11:01:00Z", ["MSFT"]),
                article(1, "Older", "2026-09-21T09:00:00Z", "2026-09-21T09:00:00Z", ["AAPL"]),
                article(1, "Older revised", "2026-09-21T09:00:00Z", "2026-09-21T10:00:00Z", ["AAPL"]),
                article(3, "Unrelated", "2026-09-21T08:00:00Z", "2026-09-21T08:00:00Z", ["TSLA"]),
            ]
        }

    monkeypatch.setattr(client, "_request", fake_request)

    articles = client.get_watchlist_news(["MSFT", "AAPL"])

    assert [item.article_id for item in articles] == [2, 1]
    assert articles[1].headline == "Older revised"
    assert requested["path"] == "/v1beta1/news"
    assert requested["params"] == {
        "symbols": "AAPL,MSFT",
        "limit": "50",
        "sort": "desc",
        "include_content": "true",
    }


def test_news_route_returns_only_watchlist_symbols_and_full_alpaca_record(client, db_session):
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="asset-msft", symbol="MSFT", name="Microsoft", exchange="NASDAQ"),
        ]
    )
    db_session.commit()
    article_data = {
        "id": 42,
        "headline": "Apple and Microsoft",
        "source": "Benzinga",
        "symbols": ["AAPL", "MSFT", "SPY"],
    }
    article = NewsArticle(
        article_id=42,
        headline="Apple and Microsoft",
        summary="A summary",
        created_at=datetime.fromisoformat("2026-09-21T09:00:00+00:00"),
        updated_at=datetime.fromisoformat("2026-09-21T09:30:00+00:00"),
        symbols=["AAPL", "MSFT", "SPY"],
        raw_data=article_data,
    )

    class FakeAlpacaClient:
        def get_watchlist_news(self, symbols):
            assert symbols == ["AAPL", "MSFT"]
            return [article]

    app.dependency_overrides[get_alpaca_market_data_client] = lambda: FakeAlpacaClient()
    response = client.get("/api/news", headers={"Authorization": f"Bearer {settings.dashboard_api_key}"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 42,
            "headline": "Apple and Microsoft",
            "summary": "A summary",
            "createdAt": "2026-09-21T09:00:00Z",
            "updatedAt": "2026-09-21T09:30:00Z",
            "watchlistSymbols": ["AAPL", "MSFT"],
            "rawData": article_data,
        }
    ]


def article(article_id, headline, created_at, updated_at, symbols):
    return {
        "id": article_id,
        "headline": headline,
        "summary": "Summary",
        "created_at": created_at,
        "updated_at": updated_at,
        "symbols": symbols,
    }
