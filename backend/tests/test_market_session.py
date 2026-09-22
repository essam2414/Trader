"""US equity market-session calendar classification and route coverage."""

from datetime import datetime

from app.alpaca_market_data import NEW_YORK, AlpacaMarketDataClient, MarketSessionStatus, TradingSession
from app.config import settings
from app.dependencies import get_alpaca_market_data_client
from app.main import app


def session(day: str, closes_at: str = "16:00") -> TradingSession:
    return TradingSession(
        opens_at=datetime.fromisoformat(f"{day}T09:30:00").replace(tzinfo=NEW_YORK),
        closes_at=datetime.fromisoformat(f"{day}T{closes_at}:00").replace(tzinfo=NEW_YORK),
    )


def test_market_session_uses_exchange_hours_during_uk_us_dst_mismatch(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    monkeypatch.setattr(
        client, "_load_calendar", lambda _day: {datetime(2026, 3, 23).date(): session("2026-03-23")}
    )

    status = client.get_market_session(datetime.fromisoformat("2026-03-23T13:45:00+00:00"))

    assert status.phase == "regular"
    assert status.ends_at == datetime.fromisoformat("2026-03-23T16:00:00-04:00")
    assert status.is_early_close is False


def test_market_session_skips_overnight_before_a_holiday(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    monkeypatch.setattr(
        client,
        "_load_calendar",
        lambda _day: {
            datetime(2026, 11, 27).date(): session("2026-11-27", "13:00"),
            datetime(2026, 11, 30).date(): session("2026-11-30"),
        },
    )

    status = client.get_market_session(datetime.fromisoformat("2026-11-26T01:00:00+00:00"))

    assert status.phase == "closed"
    assert status.next_phase == "overnight"
    assert status.next_phase_starts_at == datetime.fromisoformat("2026-11-26T20:00:00-05:00")


def test_market_session_does_not_show_after_hours_after_an_early_close(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    monkeypatch.setattr(
        client,
        "_load_calendar",
        lambda _day: {
            datetime(2026, 11, 27).date(): session("2026-11-27", "13:00"),
            datetime(2026, 11, 30).date(): session("2026-11-30"),
        },
    )

    status = client.get_market_session(datetime.fromisoformat("2026-11-27T18:30:00+00:00"))

    assert status.phase == "closed"
    assert status.next_phase == "overnight"
    assert status.next_phase_starts_at == datetime.fromisoformat("2026-11-29T20:00:00-05:00")


def test_market_session_route_returns_the_client_schedule(client):
    class FakeMarketDataClient:
        def get_market_session(self):
            return MarketSessionStatus(
                phase="regular",
                as_of=datetime.fromisoformat("2026-09-18T14:00:00+00:00"),
                ends_at=datetime.fromisoformat("2026-09-18T20:00:00+00:00"),
                next_phase="after_hours",
                next_phase_starts_at=datetime.fromisoformat("2026-09-18T20:00:00+00:00"),
                is_early_close=False,
            )

    app.dependency_overrides[get_alpaca_market_data_client] = FakeMarketDataClient

    response = client.get(
        "/api/market-session", headers={"Authorization": f"Bearer {settings.dashboard_api_key}"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "phase": "regular",
        "asOf": "2026-09-18T14:00:00Z",
        "endsAt": "2026-09-18T20:00:00Z",
        "nextPhase": "after_hours",
        "nextPhaseStartsAt": "2026-09-18T20:00:00Z",
        "isEarlyClose": False,
    }
