"""Collect, group, and publish source-backed watchlist catalyst stories."""

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    NewsCollectionRun,
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsStoryStock,
    NewsSyncState,
    WatchlistEntry,
)
from .news_ai import Evidence, OpenAINewsAnalyser
from .news_dates import better_release_date as _better_release_date
from .news_identity import same_analyst_event
from .news_resolution import (
    COVERED,
    check_publication,
    compatible,
    describe,
    descriptor_for,
    find_development,
    identity_key,
    reconcile_developments,
    record_decision,
    remember,
)
from .news_sources import (
    NewsHttp,
    SourceItem,
    alpaca_items,
    canonical_url,
    company_match,
    configured_feeds,
    finnhub_items,
    rss_items,
    sec_items,
    spglobal_index_items,
)
from .news_web_search import OpenAIWebNewsDiscovery

logger = logging.getLogger(__name__)
WEB_SEARCH_MIN_INTERVAL = timedelta(hours=6)

NEGATIVE = (
    "cuts guidance",
    "lowers guidance",
    "downgrade",
    "recall",
    "offering",
    "dilution",
    "misses",
    "investigation",
    "sanctions",
    "lawsuit",
    "contract loss",
)
POSITIVE = (
    "raises guidance",
    "upgrade",
    "approval",
    "wins contract",
    "acquisition",
    "index addition",
    "beats",
)
CATEGORY_WORDS = {
    "earnings": ("earnings", "quarterly results", "revenue", "eps"),
    "guidance": ("guidance", "outlook", "forecast"),
    "deal": ("deal", "contract", "agreement", "partnership", "acquisition", "merger"),
    "analyst": ("price target", "analyst", "upgrade", "downgrade", "coverage", "rating", "initiates"),
    "financing": ("offering", "dilution", "form s-3", "form f-3", "form s-1", "form 424b5", "form 424b4"),
    "insider": ("insider sale", "insider selling", "form 4"),
    "regulatory": ("fda", "approval", "lawsuit", "investigation", "recall"),
    "index": ("s&p 500", "nasdaq 100", "index addition", "join the index"),
    "geopolitical": ("tariff", "sanction", "ceasefire", "war", "oil supply"),
}
CATALYST_WORDS = re.compile(
    r"\b(?:earnings|results|revenue|profit|loss|eps|guidance|outlook|forecast|contract|deal|"
    r"agreement|partnership|acquir(?:e|es|ed|ing)|acquisition|merger|takeover|price target|upgrade|downgrade|"
    r"initiates? coverage|initiated coverage|starts? coverage|begins? coverage|buy rating|sell rating|"
    r"initiates?.{0,80}\bat (?:buy|sell|hold)|"
    r"approval|fda|trial|recall|investigation|lawsuit|settlement|index|s&p 500|nasdaq 100|"
    r"sanction|tariff|ceasefire|war|oil supply|oil price|opec|buyback|dividend|offering|"
    r"financing|debt|ceo|cfo|layoff|bankrupt|restatement|trillion|valuation|market cap|"
    r"form 8-k|form 6-k|form 10-q|form 10-k|form 4|form s-3(?:asr)?|"
    r"form f-3(?:asr)?|form s-1|"
    r"form 424b4|form 424b5|dilution|dilutive|secondary offering|shelf registration|"
    r"at-the-market|insider sale|insider selling|share sale|chip supply|wafer|advanced packaging|"
    r"gpu supply|data center|hyperscaler|cloud spending|software spending|saas demand|"
    r"optical transceiver|co-packaged optics|800g optics|1\.6t optics|hbm|dram prices|nand prices|"
    r"enterprise ssd|power distribution|grid constraints|"
    r"capital expenditure|capex|launch|unveil|introduce|order|award|export restriction|"
    r"production capacity|hdd capacity|hdd supply|capacity expansion)\b",
    re.I,
)


def _category(title: str) -> str:
    lower = title.lower()
    return next(
        (kind for kind, words in CATEGORY_WORDS.items() if any(word in lower for word in words)), "other"
    )


def _utc(value: datetime) -> datetime:
    """SQLite drops timezone data in tests; all persisted timestamps are UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _direction(title: str) -> str:
    lower = title.lower()
    negative = any(word in lower for word in NEGATIVE)
    positive = any(word in lower for word in POSITIVE)
    if negative and positive:
        return "unclear"
    if negative:
        return "downside"
    if positive:
        return "upside"
    return "unclear"


def _story_similarity(left: str, right: str) -> float:
    stop = {"the", "a", "an", "and", "of", "to", "for", "in", "on", "stock", "shares", "says"}
    one = {word for word in re.findall(r"[a-z0-9]+", left.lower()) if word not in stop}
    two = {word for word in re.findall(r"[a-z0-9]+", right.lower()) if word not in stop}
    jaccard = len(one & two) / max(1, len(one | two))
    return max(jaccard, SequenceMatcher(None, left.lower(), right.lower()).ratio())


def _watchlist_matches(item: SourceItem, entries: list[WatchlistEntry]) -> list[WatchlistEntry]:
    provider_symbols = {symbol.upper() for symbol in item.symbols}
    text = f"{item.title} {item.excerpt[:1200]}"
    return [
        entry for entry in entries if entry.symbol.upper() in provider_symbols or company_match(text, entry)
    ]


def _upsert_source(db: Session, item: SourceItem, now: datetime) -> tuple[NewsSourceItem, bool]:
    existing = db.query(NewsSourceItem).filter_by(provider=item.provider, source_key=item.key).one_or_none()
    digest = hashlib.sha256(f"{item.title}\n{item.excerpt}".encode()).hexdigest()
    if existing:
        content_changed = existing.content_hash != digest
        if content_changed:
            # Keep immutable evidence for the earlier development. A revised article may
            # report a new event; it must pass the same novelty checks as a new URL.
            revision_key = f"{item.key[:420]}:revision:{digest}"
            return _upsert_source(db, replace(item, key=revision_key), now)
        date_found = existing.published_at is None and item.published_at is not None
        date_corrected = bool(
            item.published_at
            and existing.published_at
            and _better_release_date(
                item.published_at,
                item.published_date_precision,
                existing.published_at,
                existing.published_date_precision,
            )
        )
        event_date_found = existing.event_date is None and item.event_date is not None
        if date_found or date_corrected:
            existing.published_at = item.published_at
            existing.date_status = item.date_status if item.date_status != "unverified" else "verified"
            existing.published_date_precision = item.published_date_precision
        elif not existing.published_at and item.date_status != "unverified":
            existing.date_status = item.date_status
        if event_date_found:
            existing.event_date = item.event_date
        if date_found or date_corrected or event_date_found:
            existing.updated_at = now
        return existing, date_found or date_corrected or event_date_found
    record = NewsSourceItem(
        provider=item.provider,
        source_key=item.key,
        url=item.url,
        title=item.title,
        excerpt=item.excerpt,
        candidate_symbols=list(item.symbols),
        published_at=item.published_at,
        date_status=(item.date_status if item.date_status != "unverified" else "verified")
        if item.published_at
        else item.date_status,
        published_date_precision=item.published_date_precision if item.published_at else None,
        event_date=item.event_date,
        first_seen_at=now,
        updated_at=None,
        content_hash=digest,
    )
    db.add(record)
    db.flush()
    return record, True


def _linked_story(db: Session, item_id: int) -> NewsStory | None:
    links = db.query(NewsStorySource).filter_by(source_item_id=item_id).all()
    for link in links:
        story = db.get(NewsStory, link.story_id)
        if story and story.status != "merged":
            return story
        if story and story.merged_into_story_id:
            return db.get(NewsStory, story.merged_into_story_id)
    return None


def _candidate_story(
    db: Session, item: SourceItem, assets: list[WatchlistEntry], now: datetime
) -> NewsStory | None:
    asset_ids = {entry.alpaca_asset_id for entry in assets}
    candidates = db.query(NewsStory).filter(NewsStory.status.in_(COVERED)).order_by(NewsStory.id).all()
    descriptor = describe(item, assets)
    for story in candidates:
        story_assets = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)}
        if not asset_ids.intersection(story_assets):
            continue
        source_ids = [link.source_item_id for link in db.query(NewsStorySource).filter_by(story_id=story.id)]
        sources = db.query(NewsSourceItem).filter(NewsSourceItem.id.in_(source_ids)).all()
        same_url = [source for source in sources if source.url == item.url]
        if any(source.title == item.title and source.excerpt == item.excerpt for source in same_url):
            return story
        if same_url:
            continue
        other = descriptor_for(db, story, assets)
        if bool(descriptor) != bool(other):
            continue
        if descriptor and other:
            # Typed conflicts must never be bypassed by headline similarity.
            if not compatible(descriptor, other, item.published_at, story.released_at) and not (
                descriptor == other and descriptor.get("kind") == "analyst" and item.published_at is None
            ):
                continue
        if (
            item.published_at
            and story.released_at
            and abs(_utc(item.published_at) - _utc(story.released_at)) > timedelta(days=7)
        ):
            continue
        if any(
            same_analyst_event(
                item,
                SourceItem(
                    source.provider,
                    source.source_key,
                    source.url,
                    source.title,
                    source.excerpt,
                    source.published_at,
                    tuple(source.candidate_symbols),
                    source.date_status,
                    source.published_date_precision or "minute",
                ),
                assets,
            )
            for source in sources
        ):
            return story
        if story.category == "analyst":
            continue
        if any(
            _story_similarity(item.title, source.title) == 1.0
            and item.excerpt == source.excerpt
            and not (
                _numbers(item.title)
                and _numbers(source.title)
                and _numbers(item.title) != _numbers(source.title)
            )
            for source in sources
        ):
            return story
    return None


def _exposures() -> dict[str, list[str]]:
    try:
        raw = json.loads(settings.news_exposures_json)
        return {
            str(key).upper(): [str(value) for value in values]
            for key, values in raw.items()
            if isinstance(values, list)
        }
    except (TypeError, ValueError, AttributeError):
        return {}


def _numbers(value: str) -> set[str]:
    return set(re.findall(r"(?<!\w)\$?\d+(?:[.,]\d+)?%?", value))


def _analyse_story(
    db: Session, story: NewsStory, entries: list[WatchlistEntry], analyser: OpenAINewsAnalyser, now: datetime
) -> None:
    source_ids = [row.source_item_id for row in db.query(NewsStorySource).filter_by(story_id=story.id)]
    sources = db.query(NewsSourceItem).filter(NewsSourceItem.id.in_(source_ids)).all()
    evidence = [
        Evidence(
            source.id,
            SourceItem(
                source.provider,
                source.source_key,
                source.url,
                source.title,
                source.excerpt,
                source.published_at,
                tuple(source.candidate_symbols),
                source.date_status,
                source.published_date_precision or "minute",
            ),
        )
        for source in sources
    ]
    candidate_ids = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)}
    result = analyser.analyse(
        [entry for entry in entries if entry.alpaca_asset_id in candidate_ids], evidence, _exposures()
    )
    if result is None:
        if story.status != "ready":
            story.status = "resolving" if story.status == "resolving" else "pending"
        return
    if not result.relevant:
        story.status = "irrelevant"
        return
    if not check_publication(db, story, analyser, now):
        if story.status == "resolving":
            analyser.last_failure_reason = "Checking for new facts; duplicate comparison is incomplete"
        return
    story.headline = result.headline
    story.short_summary = result.shortSummary
    story.detail_summary = result.detailSummary
    story.relevance_reason = result.relevanceReason
    story.key_facts = result.keyFacts
    story.unknowns = result.unknowns
    story.category = result.category
    story.direction = result.direction
    story.model_version = analyser.model
    story.status = "ready"
    story.summary_dirty = False
    story.updated_at = now
    db.query(NewsStoryStock).filter_by(story_id=story.id).delete()
    for asset_id in set(result.affectedAssetIds):
        db.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=asset_id))


def ingest_items(
    db: Session,
    items: list[SourceItem],
    entries: list[WatchlistEntry],
    analyser: OpenAINewsAnalyser,
    now: datetime,
    analysis_budget: list[int] | None = None,
) -> int:
    """Idempotently persist candidates; source timestamps never come from the model."""
    processed = 0
    for item in items:
        if not canonical_url(item.url) or not item.title:
            continue
        if not CATALYST_WORDS.search(f"{item.title} {item.excerpt[:1000]}"):
            continue
        assets = _watchlist_matches(item, entries)
        if not assets:
            continue
        source, changed = _upsert_source(db, item, now)
        if not changed and _linked_story(db, source.id):
            continue
        revised = ":revision:" in source.source_key
        matched, descriptor, ambiguous = (
            find_development(db, item, assets) if not revised else (None, {}, True)
        )
        story = _linked_story(db, source.id) or matched
        if story is None and not ambiguous:
            story = _candidate_story(db, item, assets, now)
        is_new = story is None
        if story is None:
            has_history = (
                db.query(NewsStory)
                .join(NewsStoryStock)
                .filter(
                    NewsStory.status.in_(COVERED),
                    NewsStoryStock.alpaca_asset_id.in_([asset.alpaca_asset_id for asset in assets]),
                )
                .first()
                is not None
            )
            story = NewsStory(
                headline=item.title,
                short_summary=item.excerpt[:450],
                detail_summary="",
                relevance_reason="",
                key_facts=[],
                unknowns=[],
                category=_category(item.title),
                direction=_direction(item.title),
                status="resolving"
                if ambiguous or (has_history and not identity_key(descriptor))
                else "pending",
                released_at=item.published_at,
                released_date_precision=item.published_date_precision if item.published_at else None,
                first_seen_at=now,
                updated_at=now,
            )
            db.add(story)
            db.flush()
        remember(db, story, descriptor)
        if not db.query(NewsStorySource).filter_by(story_id=story.id, source_item_id=source.id).first():
            db.add(NewsStorySource(story_id=story.id, source_item_id=source.id))
            if story.status == "ready":
                story.summary_dirty = True
        if story.event_date is None:
            story.event_date = item.event_date or source.event_date
        for asset in assets:
            if (
                not db.query(NewsStoryStock)
                .filter_by(story_id=story.id, alpaca_asset_id=asset.alpaca_asset_id)
                .first()
            ):
                db.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=asset.alpaca_asset_id))
        if item.published_at and _better_release_date(
            item.published_at,
            item.published_date_precision,
            story.released_at,
            story.released_date_precision,
        ):
            story.released_at = item.published_at
            story.released_date_precision = item.published_date_precision
        db.flush()
        record_decision(
            db,
            story,
            "unresolved" if story.status == "resolving" else "new" if is_new else "additional_coverage",
            "Source identity resolved" if story.status != "resolving" else "Awaiting novelty check",
            now,
        )
        if story.status == "expired":
            processed += 1
            continue
        if analysis_budget is not None and analysis_budget[0] <= 0:
            if story.status not in {"ready", "resolving"}:
                story.status = "pending"
        else:
            _analyse_story(db, story, entries, analyser, now)
            if analysis_budget is not None:
                analysis_budget[0] -= 1
        processed += 1
    reconcile_developments(db, now, apply=True)
    db.commit()
    return processed


def retry_pending(
    db: Session,
    entries: list[WatchlistEntry],
    analyser: OpenAINewsAnalyser,
    now: datetime,
    budget: list[int],
    force: bool = False,
) -> int:
    retried = 0
    if budget[0] <= 0:
        return retried
    reconcile_developments(db, now, apply=True)
    db.commit()
    for story in (
        db.query(NewsStory)
        .filter(
            NewsStory.status.in_(("pending", "resolving"))
            | ((NewsStory.status == "ready") & NewsStory.summary_dirty)
        )
        .order_by(NewsStory.first_seen_at, NewsStory.id)
        .all()
    ):
        if story.status == "merged":
            continue
        if not story.identity_version and not story.event_descriptor and story.status == "pending":
            story.status = "resolving"
            db.commit()
        if budget[0] <= 0:
            break
        if not {entry.alpaca_asset_id for entry in entries}.intersection(
            row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)
        ):
            continue
        state_key = f"analysis:{story.id}"
        state = db.get(NewsSyncState, state_key)
        if not force and state and state.next_attempt_at and now < _utc(state.next_attempt_at):
            continue
        _analyse_story(db, story, entries, analyser, now)
        if story.status in {"pending", "resolving"} or story.summary_dirty:
            if state is None:
                state = NewsSyncState(source_key=state_key)
                db.add(state)
            state.last_attempt_at = now
            state.last_error = (
                getattr(analyser, "last_failure_reason", None) or "Summary analysis did not complete"
            )
            state.last_outcome = "failure"
            state.next_attempt_at = now + timedelta(minutes=30)
        elif state is not None:
            db.delete(state)
        # The next token reservation writes through a separate session. Release this story's
        # transaction first so SQLite does not block every remaining reservation in the batch.
        db.commit()
        budget[0] -= 1
        retried += 1
    return retried


def run_pending_analysis(db: Session, analyser: OpenAINewsAnalyser | None = None) -> int:
    """Finish source-backed summaries without collecting external news again."""
    analyser = analyser or OpenAINewsAnalyser()
    if not analyser.available():
        return 0
    entries = db.query(WatchlistEntry).all()
    if not entries:
        return 0
    pending_count = (
        db.query(NewsStory)
        .filter(NewsStory.status.in_(("pending", "resolving")) | NewsStory.summary_dirty)
        .count()
    )
    return retry_pending(db, entries, analyser, datetime.now(timezone.utc), [pending_count])


def _cooldown_until(error: Exception, now: datetime) -> datetime | None:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 403:
            return now + timedelta(days=1)
        if status == 429:
            retry_after = error.response.headers.get("retry-after", "")
            if retry_after.isdigit():
                return now + timedelta(seconds=max(60, min(int(retry_after), 3600)))
            try:
                retry_time = parsedate_to_datetime(retry_after).astimezone(timezone.utc)
                return max(now + timedelta(minutes=1), min(retry_time, now + timedelta(hours=1)))
            except (TypeError, ValueError, OverflowError):
                return now + timedelta(minutes=30)
    if isinstance(error, httpx.TimeoutException):
        return now + timedelta(minutes=15)
    if isinstance(error, ValueError) and str(error).startswith("OpenAI web search"):
        return now + timedelta(minutes=30)
    return None


def _record_source_result(db: Session, key: str, now: datetime, error: Exception | None) -> None:
    state = db.get(NewsSyncState, key)
    if state is None:
        state = NewsSyncState(source_key=key)
        db.add(state)
    state.last_attempt_at = now
    if error is None:
        state.last_success_at = now
        state.last_error = None
        state.next_attempt_at = None
        state.last_outcome = "success"
    else:
        state.last_error = str(error)[:500]
        state.next_attempt_at = _cooldown_until(error, now)
        state.last_outcome = "failure"
    db.commit()


def active_news_source_keys(entries: list[WatchlistEntry]) -> set[str]:
    keys = {f"rss:{provider}" for provider in configured_feeds()}
    keys.update({"sec", "spdji"})
    for entry in entries:
        keys.add(f"alpaca:{entry.symbol}")
        if settings.finnhub_api_key:
            keys.add(f"finnhub:{entry.symbol}")
        if (
            settings.openai_news_enabled
            and settings.openai_news_web_search_enabled
            and settings.openai_api_key
        ):
            keys.add(f"openai_web:{entry.symbol}")
    return keys


def _source_deferred(state: NewsSyncState | None, now: datetime, force: bool) -> bool:
    if not state or not state.next_attempt_at or now >= _utc(state.next_attempt_at):
        return False
    # Manual refresh bypasses cadence and ordinary retries, but cannot override
    # a provider's explicit access denial or rate limit.
    return not force or bool(state.last_error and re.search(r"\b(?:403|429)\b", state.last_error))


def run_news_sync(
    db: Session,
    analyser: OpenAINewsAnalyser | None = None,
    now: datetime | None = None,
    http: NewsHttp | None = None,
    force: bool = False,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    entries = db.query(WatchlistEntry).all()
    if not entries:
        return {}
    analyser = analyser or OpenAINewsAnalyser()
    owned_http = http is None
    http = http or NewsHttp()
    # Re-query the full bounded window. Provider feeds can add articles late, and a
    # successful run from an unrelated source must not advance another source's cursor.
    cutoff = now - timedelta(days=7)
    results: dict[str, int] = {}
    jobs: dict[str, Callable[[], list[SourceItem]]] = {}
    failed: list[str] = []
    skipped: list[str] = []
    try:
        reconcile_developments(db, now, apply=True)
        db.commit()
        ready_before_ids = {story_id for (story_id,) in db.query(NewsStory.id).filter_by(status="ready")}
        watched_symbols = {entry.symbol.upper() for entry in entries}
        for provider, url in configured_feeds().items():
            ir_symbol = provider.removeprefix("ir_").upper() if provider.startswith("ir_") else ""
            symbols = (ir_symbol,) if ir_symbol in watched_symbols else ()
            jobs[f"rss:{provider}"] = lambda url=url, provider=provider, symbols=symbols: rss_items(
                http, url, provider, symbols
            )
        if settings.finnhub_api_key:
            for entry in entries:
                jobs[f"finnhub:{entry.symbol}"] = lambda symbol=entry.symbol: finnhub_items(
                    http, symbol, cutoff, now
                )
        for entry in entries:
            jobs[f"alpaca:{entry.symbol}"] = lambda symbol=entry.symbol: alpaca_items(
                http, [symbol], cutoff, now
            )
        jobs.update(
            {
                "sec": lambda: sec_items(http, entries, cutoff),
                "spdji": lambda: spglobal_index_items(http, entries, now),
            }
        )
        web_discovery = OpenAIWebNewsDiscovery()

        def search_web(entry: WatchlistEntry) -> list[SourceItem]:
            if not owned_http:
                return web_discovery.search(entry, cutoff, now, http)
            web_http = NewsHttp()
            try:
                return web_discovery.search(entry, cutoff, now, web_http)
            finally:
                web_http.close()

        if web_discovery.available():
            for entry in entries:
                key = f"openai_web:{entry.symbol}"
                state = db.get(NewsSyncState, key)
                if (
                    not force
                    and state
                    and not state.last_error
                    and state.last_attempt_at
                    and now - _utc(state.last_attempt_at) < WEB_SEARCH_MIN_INTERVAL
                ):
                    skipped.append(key)
                    continue
                jobs[key] = lambda entry=entry: search_web(entry)
        web_keys = [key for key in jobs if key.startswith("openai_web:")]
        executor = ThreadPoolExecutor(max_workers=min(4, len(web_keys))) if owned_http and web_keys else None
        try:
            web_futures = {
                key: executor.submit(jobs[key])
                for key in web_keys
                if executor and not _source_deferred(db.get(NewsSyncState, key), now, force)
            }
            for key, job in jobs.items():
                state = db.get(NewsSyncState, key)
                if _source_deferred(state, now, force):
                    skipped.append(key)
                    continue
                try:
                    items = web_futures[key].result() if key in web_futures else job()
                    results[key] = ingest_items(db, items, entries, analyser, now, [0])
                    _record_source_result(db, key, now, None)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    db.rollback()
                    failed.append(key)
                    logger.warning("News source %s failed: %s", key, exc)
                    _record_source_result(db, key, now, exc)
        finally:
            if executor:
                executor.shutdown(wait=True)
        pending_count = (
            db.query(NewsStory)
            .filter(NewsStory.status.in_(("pending", "resolving")) | NewsStory.summary_dirty)
            .count()
        )
        budget = [
            pending_count if not isinstance(analyser, OpenAINewsAnalyser) or analyser.available() else 0
        ]
        results["pending_retried"] = retry_pending(db, entries, analyser, now, budget, force=force)
        reconcile_developments(db, now, apply=True)
        new_source_count = db.query(NewsSourceItem).filter(NewsSourceItem.first_seen_at == now).count()
        ready_after_ids = {story_id for (story_id,) in db.query(NewsStory.id).filter_by(status="ready")}
        new_card_count = len(ready_after_ids - ready_before_ids)
        db.add(
            NewsCollectionRun(
                started_at=now,
                completed_at=datetime.now(timezone.utc),
                attempted_count=len(results) - 1 + len(failed),
                success_count=len(results) - 1,
                failure_count=len(failed),
                skipped_count=len(skipped),
                new_source_count=new_source_count,
                new_card_count=new_card_count,
                failed_sources=failed,
                skipped_sources=skipped,
            )
        )
        db.commit()
    finally:
        if owned_http:
            http.close()
    return results
