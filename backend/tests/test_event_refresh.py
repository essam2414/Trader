"""Manual events collection through the authenticated API."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import NewsSyncState, WatchlistEntry
from app.services.news_events import EventCandidate, upsert_events


def test_manual_refresh_collects_events_and_reports_partial_source_failure(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "news_enabled", True)
    db_session.add(
        WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme", exchange="NASDAQ")
    )
    db_session.commit()
    monkeypatch.setattr("app.scheduler.SessionLocal", sessionmaker(bind=db_session.get_bind()))
    calls = []

    def collect(db):
        calls.append("collected")
        now = datetime.now(timezone.utc)
        upsert_events(
            db,
            [
                EventCandidate(
                    "earnings:asset-acme:2026-Q4",
                    "Acme earnings report",
                    "earnings",
                    "watchlist",
                    date.today() + timedelta(days=7),
                    None,
                    "date_only",
                    "estimated",
                    "https://example.com/calendar",
                    ("asset-acme",),
                )
            ],
            now,
        )
        db.add(NewsSyncState(source_key="events:fed", last_attempt_at=now, last_error="Provider unavailable"))
        db.commit()
        return {"events:earnings": 1}

    monkeypatch.setattr("app.services.news_events.run_events_sync", collect)
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}

    assert client.post("/api/events/refresh").status_code == 401
    response = client.post("/api/events/refresh", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "refreshedSources": 1,
        "refreshedEvents": 1,
        "failedSources": ["events:fed"],
    }
    assert calls == ["collected"]
    assert client.get("/api/events", headers=headers).json()[0]["title"] == "Acme earnings report"


def test_manual_refresh_rejects_disabled_or_overlapping_collection(client, monkeypatch):
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}
    monkeypatch.setattr(settings, "news_enabled", False)
    assert client.post("/api/events/refresh", headers=headers).status_code == 503

    monkeypatch.setattr(settings, "news_enabled", True)
    monkeypatch.setattr("app.routers.news.run_events_job", lambda: None)
    assert client.post("/api/events/refresh", headers=headers).status_code == 409
