"""Official scheduled US-market releases and watchlist earnings dates."""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import MarketEvent, MarketEventStock, NewsSourceItem, NewsSyncState, WatchlistEntry
from .news_sources import NewsHttp, canonical_url, company_match, plain_text

NEW_YORK = ZoneInfo("America/New_York")
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_URL = "https://apps.bea.gov/API/signup/release_dates.json"
EIA_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
AV_URL = "https://www.alphavantage.co/query"


@dataclass(frozen=True)
class EventCandidate:
    key: str
    title: str
    category: str
    scope: str
    event_date: date
    starts_at: datetime | None
    precision: str
    status: str
    url: str
    asset_ids: tuple[str, ...] = ()


def _ical_datetime(value: str, timezone_name: str | None) -> datetime | None:
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if "T" not in value:
            return None
        normalized_zone = "America/New_York" if timezone_name == "US-Eastern" else timezone_name
        zone = ZoneInfo(normalized_zone) if normalized_zone else NEW_YORK
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=zone).astimezone(timezone.utc)
    except (ValueError, KeyError):
        return None


def parse_ics(text: str) -> list[tuple[str, datetime | None, date | None, str]]:
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    result = []
    for block in unfolded.split("BEGIN:VEVENT")[1:]:
        block = block.split("END:VEVENT", 1)[0]
        fields: dict[str, tuple[str, str | None]] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            base = name.split(";", 1)[0]
            timezone_name = re.search(r"TZID=([^;:]+)", name)
            fields[base] = (value.strip(), timezone_name.group(1) if timezone_name else None)
        title = fields.get("SUMMARY", ("", None))[0].replace("\\,", ",").replace("\\n", " ")
        raw_date, zone = fields.get("DTSTART", ("", None))
        starts_at = _ical_datetime(raw_date, zone)
        day = starts_at.astimezone(NEW_YORK).date() if starts_at else None
        if not day and re.fullmatch(r"\d{8}", raw_date):
            day = datetime.strptime(raw_date, "%Y%m%d").date()
        result.append((title, starts_at, day, fields.get("URL", ("", None))[0]))
    return result


def bls_events(http: NewsHttp, today: date) -> list[EventCandidate]:
    events = []
    for title, starts_at, day, url in parse_ics(http.get(BLS_URL).text):
        lower = title.lower()
        if not day or day < today or day > today + timedelta(days=120):
            continue
        if "consumer price index" in lower:
            category = "cpi"
        elif "employment situation" in lower:
            category = "payrolls"
        elif "producer price index" in lower:
            category = "ppi"
        else:
            continue
        events.append(
            EventCandidate(
                f"bls:{category}:{day}",
                title,
                category,
                "us_market",
                day,
                starts_at,
                "exact" if starts_at else "date_only",
                "confirmed",
                url or BLS_URL,
            )
        )
    return events


def bea_events(http: NewsHttp, today: date) -> list[EventCandidate]:
    payload = http.get(BEA_URL).json()
    events = []
    for name, category in (("Gross Domestic Product", "gdp"), ("Personal Income and Outlays", "pce")):
        for raw in payload.get(name, {}).get("release_dates", []):
            try:
                starts_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            day = starts_at.astimezone(NEW_YORK).date()
            if today <= day <= today + timedelta(days=120):
                events.append(
                    EventCandidate(
                        f"bea:{category}:{day}",
                        name,
                        category,
                        "us_market",
                        day,
                        starts_at,
                        "exact",
                        "confirmed",
                        BEA_URL,
                    )
                )
    return events


def fed_events(http: NewsHttp, today: date) -> list[EventCandidate]:
    body = plain_text(http.get(FED_URL).text, limit=50000)
    events = []
    for released in re.findall(
        r"\bMinutes:\s*(?:PDF\s*\|\s*HTML\s*)?\(Released\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})\)", body, re.I
    ):
        try:
            day = datetime.strptime(released, "%B %d, %Y").date()
        except ValueError:
            continue
        if today <= day <= today + timedelta(days=365):
            events.append(
                EventCandidate(
                    f"fed:minutes:{day}",
                    "FOMC meeting minutes released",
                    "fomc_minutes",
                    "us_market",
                    day,
                    None,
                    "date_only",
                    "confirmed",
                    FED_URL,
                )
            )
    for year in (today.year, today.year + 1):
        section = re.search(
            rf"{year} FOMC Meetings(.*?)(?:{year - 1}|{year + 1}) FOMC Meetings", body, re.I | re.S
        )
        if section is None:
            section = re.search(rf"{year} FOMC Meetings(.*?)(?:####|Last Update)", body, re.I | re.S)
        if section is None:
            continue
        for month, end_day, projections in re.findall(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{1,2}-(\d{1,2})(\*)?",
            section.group(1),
            re.I,
        ):
            try:
                day = date(year, datetime.strptime(month, "%B").month, int(end_day))
            except ValueError:
                continue
            if today <= day <= today + timedelta(days=365):
                title = "FOMC policy decision"
                if projections:
                    title += " and economic projections"
                events.append(
                    EventCandidate(
                        f"fed:decision:{day}",
                        title,
                        "fomc",
                        "us_market",
                        day,
                        datetime.combine(day, time(14), NEW_YORK).astimezone(timezone.utc),
                        "exact",
                        "confirmed",
                        FED_URL,
                    )
                )
    return events


def earnings_events(http: NewsHttp, entries: list[WatchlistEntry], today: date) -> list[EventCandidate]:
    if not settings.alpha_vantage_api_key:
        return []
    response = http.get(
        AV_URL,
        params={
            "function": "EARNINGS_CALENDAR",
            "horizon": "3month",
            "apikey": settings.alpha_vantage_api_key,
        },
    )
    reader = csv.DictReader(io.StringIO(response.text))
    if not reader.fieldnames or not {"symbol", "reportDate"}.issubset(reader.fieldnames):
        raise ValueError("Alpha Vantage did not return an earnings calendar")
    by_symbol = {entry.symbol.upper(): entry for entry in entries}
    events = []
    for row in reader:
        entry = by_symbol.get(row.get("symbol", "").upper())
        if entry is None:
            continue
        try:
            day = date.fromisoformat(row["reportDate"])
        except (ValueError, KeyError):
            continue
        if today <= day <= today + timedelta(days=120):
            period = row.get("fiscalDateEnding") or f"{day.year}Q{(day.month - 1) // 3 + 1}"
            window = (row.get("timeOfTheDay") or "").lower()
            timing = (
                " before US open"
                if window == "pre-market"
                else " after US close"
                if window == "post-market"
                else ""
            )
            events.append(
                EventCandidate(
                    f"earnings:{entry.alpaca_asset_id}:{period}",
                    f"{entry.name} earnings report{timing}",
                    "earnings",
                    "watchlist",
                    day,
                    None,
                    "window" if timing else "date_only",
                    "estimated",
                    AV_URL,
                    (entry.alpaca_asset_id,),
                )
            )
    return events


def ir_calendar_events(http: NewsHttp, entry: WatchlistEntry, url: str, today: date) -> list[EventCandidate]:
    """Read an optional official company iCalendar feed keyed by stable UID."""
    text = http.get(url).text
    events = []
    for block in re.sub(r"\r?\n[ \t]", "", text).split("BEGIN:VEVENT")[1:]:
        block = block.split("END:VEVENT", 1)[0]
        fields: dict[str, str] = {}
        zone = None
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            base = key.split(";", 1)[0]
            if base == "DTSTART":
                match = re.search(r"TZID=([^;:]+)", key)
                zone = match.group(1) if match else None
            fields[base] = value.strip()
        title = fields.get("SUMMARY", "").replace("\\,", ",").replace("\\n", " ")
        starts_at = _ical_datetime(fields.get("DTSTART", ""), zone)
        day = starts_at.astimezone(NEW_YORK).date() if starts_at else None
        if day is None and re.fullmatch(r"\d{8}", fields.get("DTSTART", "")):
            day = datetime.strptime(fields["DTSTART"], "%Y%m%d").date()
        if not title or day is None or not today <= day <= today + timedelta(days=365):
            continue
        lower = title.lower()
        category = (
            "earnings"
            if any(word in lower for word in ("earnings", "results", "quarter"))
            else "investor_day"
            if "investor day" in lower
            else "shareholder_vote"
            if "shareholder" in lower or "annual meeting" in lower
            else "company_event"
        )
        uid = fields.get("UID") or f"{entry.symbol}:{title.lower()}:{day.year}"
        key = f"ir:{entry.alpaca_asset_id}:{hashlib.sha256(uid.encode()).hexdigest()[:24]}"
        source = canonical_url(fields.get("URL", "")) or url
        events.append(
            EventCandidate(
                key,
                title,
                category,
                "watchlist",
                day,
                starts_at,
                "exact" if starts_at else "date_only",
                "cancelled" if fields.get("STATUS") == "CANCELLED" else "confirmed",
                source,
                (entry.alpaca_asset_id,),
            )
        )
    return events


def index_events(db: Session, entries: list[WatchlistEntry], today: date) -> list[EventCandidate]:
    """Surface explicit effective dates from official index-announcement excerpts."""
    events = []
    sources = db.query(NewsSourceItem).filter_by(provider="spdji").all()
    pattern = re.compile(
        r"\beffective\b.{0,80}?\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),?\s+(20\d{2})",
        re.I | re.S,
    )
    for source in sources:
        text = f"{source.title} {source.excerpt}"
        if not re.search(r"\b(?:join|add|inclusion|included|replace)\b", text, re.I):
            continue
        match = pattern.search(text)
        if not match:
            continue
        try:
            day = date(
                int(match.group(3)), datetime.strptime(match.group(1), "%B").month, int(match.group(2))
            )
        except ValueError:
            continue
        if not today <= day <= today + timedelta(days=365):
            continue
        for entry in entries:
            if company_match(text, entry):
                events.append(
                    EventCandidate(
                        f"index:{entry.alpaca_asset_id}:{source.id}",
                        f"{entry.name} index change takes effect",
                        "index",
                        "watchlist",
                        day,
                        None,
                        "date_only",
                        "confirmed",
                        source.url,
                        (entry.alpaca_asset_id,),
                    )
                )
    return events


def eia_events(
    http: NewsHttp, today: date, entries: list[WatchlistEntry], exposures: dict[str, list[str]]
) -> list[EventCandidate]:
    relevant = [
        entry
        for entry in entries
        if any(
            "oil" in tag.lower() or "energy" in tag.lower() for tag in exposures.get(entry.symbol.upper(), [])
        )
    ]
    if not relevant:
        return []
    text = plain_text(http.get(EIA_URL).text, limit=30000)
    if "10:30" not in text or "Wednesday" not in text:
        raise ValueError("EIA schedule could not be verified")
    # Avoid publishing a wrong regular Wednesday date in a holiday week.
    alternate_dates: dict[date, tuple[date, time]] = {}
    month = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    pattern = (
        rf"({month} \d{{1,2}}, \d{{4}})\s+({month} \d{{1,2}}, \d{{4}})"
        r"\s+\w+\s+(\d{1,2}:\d{2})\s+([ap])\.m\."
    )
    for week_end, release, clock, period in re.findall(pattern, text, re.I):
        try:
            week_end_date = datetime.strptime(week_end, "%B %d, %Y").date()
            release_date = datetime.strptime(release, "%B %d, %Y").date()
            hour, minute = map(int, clock.split(":"))
            alternate_dates[week_end_date + timedelta(days=5)] = (
                release_date,
                time((hour % 12) + (12 if period.lower() == "p" else 0), minute),
            )
        except ValueError:
            continue
    events = []
    for offset in range(1, 60):
        day = today + timedelta(days=offset)
        if day.weekday() != 2:
            continue
        if day in alternate_dates:
            continue
        events.append(
            EventCandidate(
                f"eia:petroleum:{day}",
                "EIA weekly petroleum status report",
                "oil_inventories",
                "watchlist",
                day,
                datetime.combine(day, time(10, 30), NEW_YORK).astimezone(timezone.utc),
                "exact",
                "confirmed",
                EIA_URL,
                tuple(entry.alpaca_asset_id for entry in relevant),
            )
        )
    for original, (day, release_time) in alternate_dates.items():
        if today <= day <= today + timedelta(days=60):
            events.append(
                EventCandidate(
                    f"eia:petroleum:{original}",
                    "EIA weekly petroleum status report",
                    "oil_inventories",
                    "watchlist",
                    day,
                    datetime.combine(day, release_time, NEW_YORK).astimezone(timezone.utc),
                    "exact",
                    "confirmed",
                    EIA_URL,
                    tuple(entry.alpaca_asset_id for entry in relevant),
                )
            )
    return events


def upsert_events(db: Session, events: list[EventCandidate], now: datetime) -> int:
    by_key = {event.key: event for event in events}
    for candidate in by_key.values():
        record = db.get(MarketEvent, candidate.key)
        if record is None:
            record = MarketEvent(
                event_key=candidate.key,
                title=candidate.title,
                category=candidate.category,
                scope=candidate.scope,
                event_date=candidate.event_date,
                starts_at=candidate.starts_at,
                time_precision=candidate.precision,
                date_status=candidate.status,
                source_url=candidate.url,
                last_verified_at=now,
            )
            db.add(record)
            db.flush()
        else:
            record.title = candidate.title
            if record.event_date != candidate.event_date:
                record.previous_event_date = record.event_date
                record.date_status = "cancelled" if candidate.status == "cancelled" else "changed"
            elif candidate.status == "cancelled":
                record.date_status = "cancelled"
            elif record.date_status != "changed":
                record.date_status = candidate.status
            record.event_date = candidate.event_date
            record.starts_at = candidate.starts_at
            record.time_precision = candidate.precision
            record.source_url = candidate.url
            record.last_verified_at = now
        db.query(MarketEventStock).filter_by(event_key=candidate.key).delete()
        for asset_id in set(candidate.asset_ids):
            db.add(MarketEventStock(event_key=candidate.key, alpaca_asset_id=asset_id))
    db.commit()
    return len(by_key)


def retire_missing_events(db: Session, job_key: str, returned_keys: set[str], today: date) -> None:
    prefix = {
        "events:bls": "bls:",
        "events:bea": "bea:",
        "events:fed": "fed:",
        "events:earnings": "earnings:",
        "events:eia": "eia:",
        "events:index": "index:",
    }.get(job_key)
    if job_key.startswith("events:ir:"):
        prefix = "ir:"
    if prefix is None:
        return
    for event in db.query(MarketEvent).filter(MarketEvent.event_date >= today).all():
        if not event.event_key.startswith(prefix) or event.event_key in returned_keys:
            continue
        if job_key.startswith("events:ir:"):
            symbol = job_key.rsplit(":", 1)[1]
            matches = db.query(WatchlistEntry).filter_by(symbol=symbol).all()
            if not any(event.event_key.startswith(f"ir:{entry.alpaca_asset_id}:") for entry in matches):
                continue
        event.date_status = "cancelled"


def run_events_sync(db: Session, now: datetime | None = None, http: NewsHttp | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NEW_YORK).date()
    entries = db.query(WatchlistEntry).all()
    try:
        from .news_digest import _exposures

        exposures = _exposures()
    except (ValueError, TypeError):
        exposures = {}
    owned_http = http is None
    http = http or NewsHttp()
    jobs = {
        "events:bls": lambda: bls_events(http, today),
        "events:bea": lambda: bea_events(http, today),
        "events:fed": lambda: fed_events(http, today),
        "events:earnings": lambda: earnings_events(http, entries, today),
        "events:eia": lambda: eia_events(http, today, entries, exposures),
        "events:index": lambda: index_events(db, entries, today),
    }
    try:
        ir_feeds = json.loads(settings.news_ir_event_feeds_json)
        if not isinstance(ir_feeds, dict):
            raise ValueError("NEWS_IR_EVENT_FEEDS_JSON must be an object")
        for entry in entries:
            url = ir_feeds.get(entry.symbol.upper())
            if isinstance(url, str) and canonical_url(url):
                jobs[f"events:ir:{entry.symbol.upper()}"] = lambda entry=entry, url=url: ir_calendar_events(
                    http, entry, url, today
                )
    except (ValueError, TypeError):
        pass
    results = {}
    try:
        for key, job in jobs.items():
            state = db.get(NewsSyncState, key)
            if state is None:
                state = NewsSyncState(source_key=key)
                db.add(state)
            state.last_attempt_at = now
            try:
                events = job()
                results[key] = upsert_events(db, events, now)
                retire_missing_events(db, key, {event.key for event in events}, today)
                state.last_success_at = now
                state.last_error = None
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                db.rollback()
                state = db.get(NewsSyncState, key) or NewsSyncState(source_key=key)
                db.add(state)
                state.last_attempt_at = now
                state.last_error = str(exc)[:500]
            db.commit()
    finally:
        if owned_http:
            http.close()
    return results
