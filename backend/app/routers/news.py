"""Persisted, read-only watchlist catalyst cards and upcoming events."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..config import settings
from ..dependencies import get_db
from ..models import (
    MarketEvent,
    MarketEventStock,
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsStoryStock,
    NewsSyncState,
    WatchlistEntry,
)
from ..scheduler import run_events_job
from ..schemas import (
    CatalystCardOut,
    CatalystDetailOut,
    CatalystSourceOut,
    EventRefreshOut,
    MarketEventOut,
    NewsStatusOut,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _symbols(db: Session, story_id: int) -> list[str]:
    rows = (
        db.query(WatchlistEntry.symbol)
        .join(NewsStoryStock, NewsStoryStock.alpaca_asset_id == WatchlistEntry.alpaca_asset_id)
        .filter(NewsStoryStock.story_id == story_id)
        .all()
    )
    return sorted({symbol for (symbol,) in rows})


def _card(db: Session, story: NewsStory) -> CatalystCardOut:
    return CatalystCardOut(
        id=story.id,
        headline=story.headline,
        shortSummary=story.short_summary,
        watchlistSymbols=_symbols(db, story.id),
        category=story.category,
        direction=story.direction,
        status=story.status,
        releasedAt=_utc(story.released_at),
        firstSeenAt=_utc(story.first_seen_at),
        updatedAt=_utc(story.updated_at),
    )


@router.get("/news", response_model=list[CatalystCardOut])
def list_news(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CatalystCardOut]:
    stories = (
        db.query(NewsStory)
        .join(NewsStoryStock)
        .join(WatchlistEntry, WatchlistEntry.alpaca_asset_id == NewsStoryStock.alpaca_asset_id)
        .filter(NewsStory.status != "irrelevant")
        .distinct()
        .order_by(NewsStory.released_at.desc(), NewsStory.first_seen_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_card(db, story) for story in stories]


@router.get("/news/status", response_model=NewsStatusOut)
def news_status(db: Session = Depends(get_db)) -> NewsStatusOut:
    states = db.query(NewsSyncState).filter(~NewsSyncState.source_key.startswith("events:")).all()
    successes = [state.last_success_at for state in states if state.last_success_at]
    return NewsStatusOut(
        lastSuccessfulRunAt=max(_utc(value) for value in successes) if successes else None,
        failedSources=sorted(state.source_key for state in states if state.last_error),
        pendingSummaries=db.query(NewsStory).filter_by(status="pending").count(),
    )


@router.get("/news/{story_id}", response_model=CatalystDetailOut)
def news_detail(story_id: int, db: Session = Depends(get_db)) -> CatalystDetailOut:
    story = db.get(NewsStory, story_id)
    if story is None or story.status == "irrelevant" or not _symbols(db, story_id):
        raise HTTPException(status_code=404, detail="News story not found")
    links = (
        db.query(NewsSourceItem)
        .join(NewsStorySource, NewsStorySource.source_item_id == NewsSourceItem.id)
        .filter(NewsStorySource.story_id == story_id)
        .order_by(NewsSourceItem.published_at)
        .all()
    )
    return CatalystDetailOut(
        **_card(db, story).model_dump(),
        detailSummary=story.detail_summary,
        relevanceReason=story.relevance_reason,
        keyFacts=story.key_facts,
        unknowns=story.unknowns,
        sources=[
            CatalystSourceOut(
                title=source.title,
                provider=source.provider,
                url=source.url,
                publishedAt=_utc(source.published_at),
            )
            for source in links
        ],
    )


@router.post("/events/refresh", response_model=EventRefreshOut)
def refresh_events(db: Session = Depends(get_db)) -> EventRefreshOut:
    if not settings.news_enabled:
        raise HTTPException(status_code=503, detail="Events collection is disabled")
    started_at = datetime.now(timezone.utc)
    result = run_events_job()
    if result is None:
        raise HTTPException(status_code=409, detail="Events collection is already running")
    failed_sources = sorted(
        state.source_key
        for state in db.query(NewsSyncState)
        .filter(
            NewsSyncState.source_key.startswith("events:"),
            NewsSyncState.last_attempt_at >= started_at,
            NewsSyncState.last_error.is_not(None),
        )
        .all()
    )
    if not result:
        raise HTTPException(status_code=502, detail="No event sources could be refreshed")
    return EventRefreshOut(
        refreshedSources=len(result),
        refreshedEvents=sum(result.values()),
        failedSources=failed_sources,
    )


@router.get("/events", response_model=list[MarketEventOut])
def list_events(
    db: Session = Depends(get_db), days: int = Query(default=90, ge=1, le=365)
) -> list[MarketEventOut]:
    today = datetime.now(ZoneInfo("America/New_York")).date()
    events = (
        db.query(MarketEvent)
        .filter(
            MarketEvent.event_date >= today,
            MarketEvent.event_date <= today + timedelta(days=days),
            MarketEvent.date_status != "cancelled",
        )
        .order_by(MarketEvent.event_date, MarketEvent.starts_at)
        .all()
    )
    result = []
    for event in events:
        symbols = sorted(
            {
                symbol
                for (symbol,) in db.query(WatchlistEntry.symbol)
                .join(MarketEventStock, MarketEventStock.alpaca_asset_id == WatchlistEntry.alpaca_asset_id)
                .filter(MarketEventStock.event_key == event.event_key)
                .all()
            }
        )
        if event.scope != "us_market" and not symbols:
            continue
        result.append(
            MarketEventOut(
                id=event.event_key,
                title=event.title,
                category=event.category,
                scope=event.scope,
                eventDate=event.event_date.isoformat(),
                previousEventDate=event.previous_event_date.isoformat()
                if event.previous_event_date
                else None,
                startsAt=_utc(event.starts_at),
                timePrecision=event.time_precision,
                dateStatus=event.date_status,
                watchlistSymbols=symbols,
                sourceUrl=event.source_url,
                lastVerifiedAt=_utc(event.last_verified_at),
            )
        )
    return result
