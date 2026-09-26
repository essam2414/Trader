"""Official calendar parsing, stock scoping, and schedule revisions."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.config import settings
from app.models import MarketEvent, NewsSourceItem, WatchlistEntry
from app.services.news_events import (
    BEA_URL,
    BLS_URL,
    FED_URL,
    EventCandidate,
    bea_events,
    bls_events,
    earnings_events,
    fed_events,
    index_events,
    ir_calendar_events,
    retire_missing_events,
    upsert_events,
)


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads

    def get(self, url, **_kwargs):
        content = self.payloads[url]
        return SimpleNamespace(text=content if isinstance(content, str) else "", json=lambda: content)


def test_official_macro_calendars_preserve_us_eastern_release_time():
    today = date(2026, 9, 25)
    http = FakeHttp(
        {
            BLS_URL: (
                "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Consumer Price Index\n"
                "DTSTART;TZID=US-Eastern:20261013T083000\nEND:VEVENT\n"
                "BEGIN:VEVENT\nSUMMARY:Minor survey\nDTSTART;VALUE=DATE:20261014\nEND:VEVENT\nEND:VCALENDAR"
            ),
            BEA_URL: {
                "Gross Domestic Product": {"release_dates": ["2026-09-30T12:30:00+00:00"]},
                "Personal Income and Outlays": {"release_dates": ["2026-10-29T12:30:00+00:00"]},
            },
            FED_URL: "<h3>2026 FOMC Meetings</h3><div>October 27-28</div><h3>2027 FOMC Meetings</h3>",
        }
    )

    cpi = bls_events(http, today)
    assert len(cpi) == 1
    assert cpi[0].starts_at == datetime(2026, 10, 13, 12, 30, tzinfo=timezone.utc)
    assert {event.category for event in bea_events(http, today)} == {"gdp", "pce"}
    fomc = fed_events(http, today)
    assert len(fomc) == 1
    assert fomc[0].starts_at == datetime(2026, 10, 28, 18, tzinfo=timezone.utc)


def test_ir_calendar_uses_uid_across_date_change_and_records_previous_date(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    url = "https://example.com/acme.ics"
    http = FakeHttp(
        {
            url: (
                "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:earnings-2026-q3\n"
                "SUMMARY:Acme Q3 earnings call\nDTSTART;TZID=America/New_York:20261020T170000\n"
                "END:VEVENT\nEND:VCALENDAR"
            )
        }
    )
    today = date(2026, 9, 25)
    first = ir_calendar_events(http, entry, url, today)
    assert first[0].status == "confirmed"
    assert first[0].precision == "exact"
    upsert_events(db_session, first, datetime(2026, 9, 25, tzinfo=timezone.utc))

    http.payloads[url] = http.payloads[url].replace("20261020T170000", "20261021T170000")
    second = ir_calendar_events(http, entry, url, today)
    assert second[0].key == first[0].key
    upsert_events(db_session, second, datetime(2026, 9, 26, tzinfo=timezone.utc))
    event = db_session.query(MarketEvent).one()
    assert event.event_date == date(2026, 10, 21)
    assert event.previous_event_date == date(2026, 10, 20)
    assert event.date_status == "changed"

    retire_missing_events(db_session, f"events:ir:{entry.symbol}", set(), today)
    assert event.date_status == "cancelled"


def test_estimated_earnings_event_has_no_clock_time(db_session):
    candidate = EventCandidate(
        "earnings:asset-acme:2026-09-30",
        "Acme earnings",
        "earnings",
        "watchlist",
        date(2026, 10, 20),
        None,
        "date_only",
        "estimated",
        "https://example.com/calendar",
        ("asset-acme",),
    )
    upsert_events(db_session, [candidate], datetime.now(timezone.utc))
    event = db_session.query(MarketEvent).one()
    assert event.starts_at is None
    assert event.time_precision == "date_only"
    assert event.date_status == "estimated"


def test_official_index_announcement_creates_only_watched_effective_date(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.add(
        NewsSourceItem(
            provider="spdji",
            source_key="index-release",
            url="https://example.com/index",
            title="Acme to join S&P 500",
            excerpt="Acme will be added effective prior to the open of trading on October 5, 2026.",
            candidate_symbols=["ACME"],
            published_at=None,
            first_seen_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
            content_hash="a" * 64,
        )
    )
    db_session.commit()
    events = index_events(db_session, [entry], date(2026, 9, 25))
    assert len(events) == 1
    assert events[0].event_date == date(2026, 10, 5)
    assert events[0].asset_ids == ("asset-acme",)


def test_alpha_vantage_csv_with_name_column_and_session_window(monkeypatch):
    monkeypatch.setattr(settings, "alpha_vantage_api_key", "test-key")
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    csv_text = (
        "symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay\n"
        "ACME,Acme Corp,2026-10-20,2026-09-30,,USD,post-market\n"
        "OTHER,Other Corp,2026-10-20,2026-09-30,,USD,pre-market\n"
    )
    http = FakeHttp({"https://www.alphavantage.co/query": csv_text})
    events = earnings_events(http, [entry], date(2026, 9, 25))
    assert len(events) == 1
    assert events[0].key == "earnings:asset-acme:2026-09-30"
    assert events[0].precision == "window"
    assert events[0].starts_at is None
    assert "after US close" in events[0].title
