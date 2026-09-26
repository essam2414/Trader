"""Collect, group, and publish source-backed watchlist catalyst stories."""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import NewsSourceItem, NewsStory, NewsStorySource, NewsStoryStock, NewsSyncState, WatchlistEntry
from .news_ai import Evidence, OpenAINewsAnalyser
from .news_sources import (
    NewsHttp,
    SourceItem,
    alpaca_items,
    bloom_energy_items,
    canonical_url,
    company_match,
    configured_feeds,
    finnhub_items,
    gdelt_exposure_items,
    gdelt_items,
    rss_items,
    sec_items,
    spglobal_index_items,
)

logger = logging.getLogger(__name__)

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
    "analyst": ("price target", "analyst", "upgrade", "downgrade"),
    "financing": ("offering", "dilution", "form s-3", "form f-3", "form s-1", "form 424b5", "form 424b4"),
    "insider": ("insider sale", "insider selling", "form 4"),
    "regulatory": ("fda", "approval", "lawsuit", "investigation", "recall"),
    "index": ("s&p 500", "nasdaq 100", "index addition", "join the index"),
    "geopolitical": ("tariff", "sanction", "ceasefire", "war", "oil supply"),
}
CATALYST_WORDS = re.compile(
    r"\b(?:earnings|results|revenue|profit|loss|eps|guidance|outlook|forecast|contract|deal|"
    r"agreement|partnership|acquir(?:e|es|ed|ing)|acquisition|merger|takeover|price target|upgrade|downgrade|"
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
    r"capital expenditure|capex|launch|unveil|introduce|order|award|export restriction)\b",
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
        changed = existing.content_hash != digest
        if changed:
            existing.title = item.title
            existing.excerpt = item.excerpt
            existing.content_hash = digest
            existing.updated_at = now
        return existing, changed
    record = NewsSourceItem(
        provider=item.provider,
        source_key=item.key,
        url=item.url,
        title=item.title,
        excerpt=item.excerpt,
        candidate_symbols=list(item.symbols),
        published_at=item.published_at,
        first_seen_at=now,
        updated_at=None,
        content_hash=digest,
    )
    db.add(record)
    db.flush()
    return record, True


def _linked_story(db: Session, item_id: int) -> NewsStory | None:
    link = db.query(NewsStorySource).filter_by(source_item_id=item_id).one_or_none()
    return db.get(NewsStory, link.story_id) if link else None


def _candidate_story(
    db: Session, item: SourceItem, assets: list[WatchlistEntry], now: datetime
) -> NewsStory | None:
    asset_ids = {entry.alpaca_asset_id for entry in assets}
    cutoff = now - timedelta(days=7)
    candidates = db.query(NewsStory).filter(NewsStory.first_seen_at >= cutoff).all()
    for story in candidates:
        story_assets = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)}
        if not asset_ids.intersection(story_assets):
            continue
        source_ids = [link.source_item_id for link in db.query(NewsStorySource).filter_by(story_id=story.id)]
        sources = db.query(NewsSourceItem).filter(NewsSourceItem.id.in_(source_ids)).all()
        if any(source.url == item.url for source in sources):
            return story
        if story.category != _category(item.title):
            continue
        if any(
            _story_similarity(item.title, source.title) >= 0.80
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
            ),
        )
        for source in sources
    ]
    candidate_ids = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)}
    result = analyser.analyse(
        [entry for entry in entries if entry.alpaca_asset_id in candidate_ids], evidence, _exposures()
    )
    if result is None:
        story.status = "pending"
        return
    if not result.relevant:
        story.status = "irrelevant"
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
        story = _linked_story(db, source.id) or _candidate_story(db, item, assets, now)
        if story is None:
            story = NewsStory(
                headline=item.title,
                short_summary=item.excerpt[:450],
                detail_summary="",
                relevance_reason="",
                key_facts=[],
                unknowns=[],
                category=_category(item.title),
                direction=_direction(item.title),
                status="pending",
                released_at=item.published_at,
                first_seen_at=now,
                updated_at=now,
            )
            db.add(story)
            db.flush()
        if not db.query(NewsStorySource).filter_by(story_id=story.id, source_item_id=source.id).first():
            db.add(NewsStorySource(story_id=story.id, source_item_id=source.id))
        for asset in assets:
            if (
                not db.query(NewsStoryStock)
                .filter_by(story_id=story.id, alpaca_asset_id=asset.alpaca_asset_id)
                .first()
            ):
                db.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=asset.alpaca_asset_id))
        if item.published_at and (
            story.released_at is None or _utc(item.published_at) < _utc(story.released_at)
        ):
            story.released_at = item.published_at
        db.flush()
        if analysis_budget is not None and analysis_budget[0] <= 0:
            story.status = "pending"
        else:
            _analyse_story(db, story, entries, analyser, now)
            if analysis_budget is not None:
                analysis_budget[0] -= 1
        processed += 1
    db.commit()
    return processed


def retry_pending(
    db: Session,
    entries: list[WatchlistEntry],
    analyser: OpenAINewsAnalyser,
    now: datetime,
    budget: list[int],
) -> int:
    retried = 0
    if budget[0] <= 0:
        return retried
    for story in (
        db.query(NewsStory)
        .filter_by(status="pending")
        .order_by(NewsStory.first_seen_at.desc())
        .limit(budget[0])
    ):
        if not {entry.alpaca_asset_id for entry in entries}.intersection(
            row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)
        ):
            continue
        _analyse_story(db, story, entries, analyser, now)
        # The next token reservation writes through a separate session. Release this story's
        # transaction first so SQLite does not block every remaining reservation in the batch.
        db.commit()
        budget[0] -= 1
        retried += 1
    return retried


def _record_source_result(db: Session, key: str, now: datetime, error: Exception | None) -> None:
    state = db.get(NewsSyncState, key)
    if state is None:
        state = NewsSyncState(source_key=key)
        db.add(state)
    state.last_attempt_at = now
    if error is None:
        state.last_success_at = now
        state.last_error = None
    else:
        state.last_error = str(error)[:500]
    db.commit()


def run_news_sync(
    db: Session,
    analyser: OpenAINewsAnalyser | None = None,
    now: datetime | None = None,
    http: NewsHttp | None = None,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    entries = db.query(WatchlistEntry).all()
    if not entries:
        return {}
    analyser = analyser or OpenAINewsAnalyser()
    owned_http = http is None
    http = http or NewsHttp()
    successes = [
        _utc(state.last_success_at)
        for state in db.query(NewsSyncState).all()
        if state.last_success_at and not state.source_key.startswith("events:")
    ]
    cutoff = (
        max(now - timedelta(days=7), min(successes) - timedelta(days=1))
        if successes
        else now - timedelta(days=7)
    )
    results: dict[str, int] = {}
    jobs: dict[str, Callable[[], list[SourceItem]]] = {}
    try:
        watched_symbols = {entry.symbol.upper() for entry in entries}
        for provider, url in configured_feeds().items():
            ir_symbol = provider.removeprefix("ir_").upper() if provider.startswith("ir_") else ""
            symbols = (ir_symbol,) if ir_symbol in watched_symbols else ()
            jobs[f"rss:{provider}"] = lambda url=url, provider=provider, symbols=symbols: (
                bloom_energy_items(http, url, symbols, now)
                if provider == "ir_be"
                else rss_items(http, url, provider, symbols)
            )
        if settings.finnhub_api_key:
            for entry in entries:
                jobs[f"finnhub:{entry.symbol}"] = lambda symbol=entry.symbol: finnhub_items(
                    http, symbol, cutoff, now
                )
        jobs.update(
            {
                "sec": lambda: sec_items(http, entries, cutoff),
                "spdji": lambda: spglobal_index_items(http, entries, now),
                "alpaca": lambda: alpaca_items(http, [entry.symbol for entry in entries], cutoff, now),
                "gdelt": lambda: gdelt_items(http, entries, cutoff, now),
                "gdelt:exposure": lambda: gdelt_exposure_items(http, entries, _exposures(), cutoff, now),
            }
        )
        for key, job in jobs.items():
            try:
                items = job()
                results[key] = ingest_items(db, items, entries, analyser, now, [0])
                _record_source_result(db, key, now, None)
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                db.rollback()
                logger.warning("News source %s failed: %s", key, exc)
                _record_source_result(db, key, now, exc)
        pending_count = db.query(NewsStory).filter_by(status="pending").count()
        budget = [
            pending_count if not isinstance(analyser, OpenAINewsAnalyser) or analyser.available() else 0
        ]
        results["pending_retried"] = retry_pending(db, entries, analyser, now, budget)
    finally:
        if owned_http:
            http.close()
    return results
