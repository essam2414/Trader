"""Persisted watchlist news routes and existing Alpaca parsing."""

from datetime import datetime, timezone

from app.alpaca_market_data import AlpacaMarketDataClient
from app.config import settings
from app.models import NewsSourceItem, NewsStory, NewsStorySource, NewsStoryStock, WatchlistEntry


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


def test_news_routes_show_one_sourced_story_only_for_current_watchlist(client, db_session):
    published = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="asset-msft", symbol="MSFT", name="Microsoft", exchange="NASDAQ"),
        ]
    )
    db_session.add(
        NewsStory(
            id=42,
            headline="Apple and Microsoft announce agreement",
            short_summary="The companies announced an agreement.",
            detail_summary="The terms were announced in a release.",
            relevance_reason="Both are named.",
            key_facts=["Both companies are named."],
            unknowns=[],
            category="deal",
            direction="unclear",
            status="ready",
            released_at=published,
            first_seen_at=published,
            updated_at=published,
        )
    )
    db_session.add(
        NewsSourceItem(
            id=7,
            provider="company",
            source_key="release-7",
            url="https://example.com/release",
            title="Agreement release",
            excerpt="The companies announced an agreement.",
            candidate_symbols=["AAPL", "MSFT"],
            published_at=published,
            first_seen_at=published,
            content_hash="a" * 64,
        )
    )
    db_session.flush()
    db_session.add_all(
        [
            NewsStoryStock(story_id=42, alpaca_asset_id="asset-aapl"),
            NewsStoryStock(story_id=42, alpaca_asset_id="asset-msft"),
            NewsStorySource(story_id=42, source_item_id=7),
        ]
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}

    cards = client.get("/api/news", headers=headers)
    assert cards.status_code == 200
    assert len(cards.json()) == 1
    assert cards.json()[0]["watchlistSymbols"] == ["AAPL", "MSFT"]
    assert cards.json()[0]["releasedAt"] == "2026-09-21T09:00:00Z"
    assert "rawData" not in cards.json()[0]

    detail = client.get("/api/news/42", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["sources"][0]["url"] == "https://example.com/release"
    assert detail.json()["detailSummary"] == "The terms were announced in a release."

    db_session.query(WatchlistEntry).delete()
    db_session.commit()
    assert client.get("/api/news", headers=headers).json() == []
    assert client.get("/api/news/42", headers=headers).status_code == 404


def article(article_id, headline, created_at, updated_at, symbols):
    return {
        "id": article_id,
        "headline": headline,
        "summary": "Summary",
        "created_at": created_at,
        "updated_at": updated_at,
        "symbols": symbols,
    }
