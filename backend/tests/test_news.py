"""Persisted watchlist news routes and existing Alpaca parsing."""

from datetime import datetime, timezone

from app.alpaca_market_data import AlpacaMarketDataClient
from app.config import settings
from app.models import (
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsStoryStock,
    NewsSyncState,
    WatchlistEntry,
)


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

    story = db_session.get(NewsStory, 42)
    story.direction = "mixed"
    db_session.commit()
    assert client.get("/api/news", headers=headers).json()[0]["direction"] == "unclear"
    assert client.get("/api/news/42", headers=headers).json()["direction"] == "unclear"

    story.status = "expired"
    db_session.commit()
    assert client.get("/api/news", headers=headers).json() == []
    assert client.get("/api/news/42", headers=headers).status_code == 404

    story.status = "ready"
    db_session.commit()
    db_session.query(WatchlistEntry).delete()
    db_session.commit()
    assert client.get("/api/news", headers=headers).json() == []
    assert client.get("/api/news/42", headers=headers).status_code == 404


def test_news_orders_before_pagination_and_hides_unresolved_developments(client, db_session):
    when = datetime(2026, 10, 3, tzinfo=timezone.utc)
    db_session.add(
        WatchlistEntry(alpaca_asset_id="asset-order", symbol="MU", name="Micron", exchange="NASDAQ")
    )
    for number, released, status in [
        (1, when, "ready"),
        (2, None, "ready"),
        (3, when, "pending"),
        (4, when, "resolving"),
    ]:
        db_session.add(
            NewsStory(
                id=number,
                headline=str(number),
                status=status,
                released_at=released,
                first_seen_at=when,
                updated_at=when,
            )
        )
        db_session.flush()
        db_session.add(NewsStoryStock(story_id=number, alpaca_asset_id="asset-order"))
    db_session.commit()
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}
    ids = [
        client.get(f"/api/news?limit=1&offset={offset}", headers=headers).json()[0]["id"]
        for offset in range(3)
    ]
    assert ids == [3, 1, 2]
    assert client.get("/api/news/4", headers=headers).status_code == 404
    assert client.get("/api/news/status", headers=headers).json()["unresolvedDevelopments"] == 1


def article(article_id, headline, created_at, updated_at, symbols):
    return {
        "id": article_id,
        "headline": headline,
        "summary": "Summary",
        "created_at": created_at,
        "updated_at": updated_at,
        "symbols": symbols,
    }


def test_news_and_events_status_use_separate_collection_times(client, db_session):
    db_session.add_all(
        [
            NewsSyncState(source_key="sec", last_success_at=datetime(2026, 9, 25, 8, tzinfo=timezone.utc)),
            NewsSyncState(source_key="gdelt:rate_limit", last_error="HTTP 429 provider cooldown"),
            NewsSyncState(
                source_key="events:fed",
                last_success_at=datetime(2026, 9, 24, 7, tzinfo=timezone.utc),
                last_error="HTTP 429 for https://example.com/calendar?token=private-value",
            ),
        ]
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}

    news = client.get("/api/news/status", headers=headers)
    events = client.get("/api/events/status", headers=headers)

    assert news.json()["lastSuccessfulRunAt"] == "2026-09-25T08:00:00Z"
    assert news.json()["failedSources"] == []
    assert news.json()["sourceErrors"] == []
    assert events.json()["lastSuccessfulRunAt"] == "2026-09-24T07:00:00Z"
    assert events.json()["failedSources"] == ["events:fed"]
    assert events.json()["sourceErrors"] == [{"source": "events:fed", "message": "HTTP 429 for [source URL]"}]
    assert "private-value" not in events.text


def test_news_status_explains_pending_summary_retry(client, db_session):
    now = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)
    db_session.add(
        NewsStory(
            id=42,
            headline="Acme wins contract",
            short_summary="",
            detail_summary="",
            relevance_reason="",
            key_facts=[],
            unknowns=[],
            category="deal",
            direction="unclear",
            status="pending",
            first_seen_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        NewsSyncState(
            source_key="analysis:42",
            last_attempt_at=now,
            last_error="AI response did not complete",
            next_attempt_at=now.replace(hour=16),
        )
    )
    db_session.commit()

    result = client.get("/api/news/status", headers={"Authorization": f"Bearer {settings.dashboard_api_key}"})

    assert result.status_code == 200
    assert result.json()["pendingSummaries"] == 1
    assert result.json()["pendingSummaryIssues"] == [
        {
            "storyId": 42,
            "headline": "Acme wins contract",
            "reason": "AI response did not complete",
            "nextRetryAt": "2026-09-27T16:00:00Z",
        }
    ]
    assert result.json()["failedSources"] == []


def test_manual_news_refresh_only_runs_news_job(client, monkeypatch):
    from app.routers import news as news_router

    monkeypatch.setattr(settings, "news_enabled", True)
    calls = []
    monkeypatch.setattr(news_router, "run_news_job", lambda *, force=False: calls.append(force) or {"sec": 2})
    monkeypatch.setattr(news_router, "run_events_job", lambda: calls.append("events") or {})
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}

    result = client.post("/api/news/refresh", headers=headers)

    assert result.status_code == 200
    assert result.json()["refreshedSources"] == 1
    assert result.json()["refreshedStories"] == 0
    assert calls == [True]
