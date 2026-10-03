"""Preview and safely consolidate duplicate stored news events."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import (
    MarketEvent,
    MarketEventStock,
    NewsEventIdentity,
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsStoryStock,
    WatchlistEntry,
)
from .news_dates import better_release_date as _better_release_date
from .news_dates import earliest_release
from .news_identity import analyst_event_key, analyst_target_action_key
from .news_sources import SourceItem


@dataclass(frozen=True)
class MergePlan:
    survivor_id: int
    duplicate_ids: tuple[int, ...]
    source_ids: tuple[int, ...]
    released_at: datetime | None
    released_date_precision: str | None = None


_PREVIEW = re.compile(
    r"\b(?:to report|set to|set for|expected to report|due to|ahead of|heads into|nears|"
    r"approach(?:es|ing)|upcoming|await(?:s|ing)|this week|next week|"
    r"may report|could report|when it reports)\b",
    re.I,
)
_EARNINGS_REPORT = re.compile(r"\b(?:earnings|results|revenue print)\b", re.I)
_QUARTER = re.compile(r"\bq([1-4])\b|\b(first|second|third|fourth)[- ]quarter\b", re.I)
_ACQUISITION = re.compile(
    r"\b(?:agrees to acquire|agreement to acquire|to acquire)\s+"
    r"([A-Za-z][A-Za-z&. -]{3,70}?)(?:\s+to\s+|\s+for\s+|[,.]|$)",
    re.I,
)


def _event_identity(story: NewsStory, entry: WatchlistEntry, events: list[MarketEvent]) -> str | None:
    if story.category == "analyst":
        item = SourceItem(
            "card",
            str(story.id),
            "https://example.com",
            story.headline,
            story.short_summary,
            story.released_at,
            (entry.symbol,),
        )
        initiation = analyst_event_key(item, entry)
        if initiation:
            return f"analyst:{initiation[0]}:{initiation[1]}:initiation:{initiation[2]}:{initiation[3]}"
        target_action = analyst_target_action_key(item, entry)
        if target_action:
            return "analyst-target:" + ":".join(target_action)
    if story.category == "deal":
        acquisition = _ACQUISITION.search(story.headline)
        if acquisition:
            target = re.sub(r"\s+", " ", acquisition.group(1).lower()).strip(" .")
            return f"deal-announcement:{entry.alpaca_asset_id}:{target}"
        return None
    if story.category not in {"earnings", "other", "analyst"}:
        return None
    description = f"{story.headline} {story.short_summary}"
    if not _EARNINGS_REPORT.search(description) or not _PREVIEW.search(description):
        return None
    published = _utc(story.released_at or story.first_seen_at)
    upcoming = [
        event
        for event in events
        if published.date() - timedelta(days=1) <= event.event_date <= published.date() + timedelta(days=45)
        and event.date_status != "cancelled"
    ]
    if upcoming:
        event = min(upcoming, key=lambda value: value.event_date)
        return f"earnings-preview:{entry.alpaca_asset_id}:{event.event_key}"
    quarter = _QUARTER.search(f"{story.headline} {story.short_summary}")
    if quarter:
        label = quarter.group(1) or str(
            ("first", "second", "third", "fourth").index(quarter.group(2).lower()) + 1
        )
        return f"earnings-preview:{entry.alpaca_asset_id}:{published.year}:q{label}"
    return None


def _near_duplicate_industry(left: NewsStory, right: NewsStory, entry: WatchlistEntry) -> bool:
    when_left = _utc(left.released_at or left.first_seen_at)
    when_right = _utc(right.released_at or right.first_seen_at)
    if abs(when_left - when_right) > timedelta(days=7):
        return False
    stop = {
        "a",
        "an",
        "and",
        "company",
        "corp",
        "expanding",
        "for",
        "has",
        "in",
        "inc",
        "is",
        "it",
        "of",
        "on",
        "outlook",
        "reshaping",
        "says",
        "shares",
        "signed",
        "stock",
        "strategic",
        "support",
        "the",
        "to",
        "with",
    }
    company = set(re.findall(r"[a-z]+", entry.name.lower())) | {entry.symbol.lower()}

    def words(value: str) -> set[str]:
        return set(re.findall(r"[a-z]+", value.lower())) - stop - company

    one, two = words(left.headline), words(right.headline)
    shared = one & two
    left_numbers = set(re.findall(r"\d+(?:\.\d+)?", left.headline))
    right_numbers = set(re.findall(r"\d+(?:\.\d+)?", right.headline))
    return (
        len(shared) >= 4
        and len(shared) / max(1, len(one | two)) >= 0.6
        and not (left_numbers and right_numbers and left_numbers != right_numbers)
    )


def plan_event_merges(db: Session) -> list[MergePlan]:
    """Consolidate only stories with the same stock-specific, identifiable event."""
    entries = {entry.alpaca_asset_id: entry for entry in db.query(WatchlistEntry)}
    event_rows = (
        db.query(MarketEvent, MarketEventStock.alpaca_asset_id)
        .join(MarketEventStock, MarketEventStock.event_key == MarketEvent.event_key)
        .filter(MarketEvent.category == "earnings")
        .all()
    )
    events_by_asset: dict[str, list[MarketEvent]] = defaultdict(list)
    for event, asset_id in event_rows:
        events_by_asset[asset_id].append(event)
    groups: dict[str, list[NewsStory]] = defaultdict(list)
    industry_by_asset: dict[str, list[NewsStory]] = defaultdict(list)
    for story in db.query(NewsStory).filter(NewsStory.status.in_(("ready", "pending"))):
        for stock in db.query(NewsStoryStock).filter_by(story_id=story.id):
            entry = entries.get(stock.alpaca_asset_id)
            if entry:
                if story.category == "industry":
                    industry_by_asset[entry.alpaca_asset_id].append(story)
                key = _event_identity(story, entry, events_by_asset.get(entry.alpaca_asset_id, []))
                if key:
                    groups[key].append(story)
    for asset_id, stories in industry_by_asset.items():
        parent = {story.id: story.id for story in stories}

        def root(story_id: int) -> int:
            while parent[story_id] != story_id:
                story_id = parent[story_id]
            return story_id

        for index, left in enumerate(stories):
            for right in stories[index + 1 :]:
                if _near_duplicate_industry(left, right, entries[asset_id]):
                    parent[root(right.id)] = root(left.id)
        for story in stories:
            groups[f"industry-similarity:{asset_id}:{root(story.id)}"].append(story)
    plans: list[MergePlan] = []
    for key, group in groups.items():
        ordered = sorted(group, key=lambda story: _utc(story.released_at or story.first_seen_at))
        clusters: list[list[NewsStory]] = []
        for story in ordered:
            if not clusters or (
                not key.startswith("earnings-preview:")
                and _utc(story.released_at or story.first_seen_at)
                - _utc(clusters[-1][0].released_at or clusters[-1][0].first_seen_at)
                > timedelta(days=7)
            ):
                clusters.append([])
            clusters[-1].append(story)
        for cluster in clusters:
            if len(cluster) < 2:
                continue

            def stock_count(story: NewsStory) -> int:
                return db.query(NewsStoryStock).filter_by(story_id=story.id).count()

            survivor = min(
                cluster,
                key=lambda story: (
                    story.status != "ready",
                    -stock_count(story) if key.startswith("industry-similarity:") else 0,
                    _utc(story.released_at or story.first_seen_at),
                    story.id,
                ),
            )
            source_ids = {
                link.source_item_id
                for story in cluster
                for link in db.query(NewsStorySource).filter_by(story_id=story.id)
            }
            dated_sources = [
                source
                for source in db.query(NewsSourceItem).filter(NewsSourceItem.id.in_(source_ids))
                if source.published_at
            ]
            earliest_source = earliest_release(dated_sources)
            plans.append(
                MergePlan(
                    survivor.id,
                    tuple(sorted(story.id for story in cluster if story.id != survivor.id)),
                    tuple(sorted(source_ids)),
                    _utc(earliest_source.published_at) if earliest_source else None,
                    earliest_source.published_date_precision if earliest_source else None,
                )
            )
    return sorted(plans, key=lambda plan: plan.survivor_id)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def plan_analyst_merges(db: Session) -> list[MergePlan]:
    """Plan merges for the same stock-specific analyst action within one event window."""
    entries = {entry.alpaca_asset_id: entry for entry in db.query(WatchlistEntry)}
    groups: dict[tuple[str, ...], dict[int, tuple[NewsStory, str]]] = defaultdict(dict)
    for story in db.query(NewsStory).filter(NewsStory.status.in_(("ready", "pending"))):
        assets = [
            entries[row.alpaca_asset_id]
            for row in db.query(NewsStoryStock).filter_by(story_id=story.id)
            if row.alpaca_asset_id in entries
        ]
        sources = (
            db.query(NewsSourceItem)
            .join(NewsStorySource, NewsStorySource.source_item_id == NewsSourceItem.id)
            .filter(NewsStorySource.story_id == story.id)
            .all()
        )
        for source in sources:
            item = SourceItem(
                source.provider,
                source.source_key,
                source.url,
                source.title,
                source.excerpt,
                source.published_at,
                tuple(source.candidate_symbols),
                source.date_status,
                source.published_date_precision or "minute",
            )
            for asset in assets:
                key = analyst_event_key(item, asset)
                if key:
                    groups[("initiation", *key[:3])][story.id] = (story, key[3])
                target_action = analyst_target_action_key(item, asset)
                if target_action:
                    groups[("target", *target_action[:4])][story.id] = (story, target_action[4])

    plans = []
    for group in groups.values():
        if len(group) < 2 or len({rating for _, rating in group.values() if rating}) > 1:
            continue
        ordered = sorted(
            (story for story, _ in group.values()),
            key=lambda story: _utc(story.released_at or story.first_seen_at),
        )
        clusters: list[list[NewsStory]] = []
        for story in ordered:
            if not clusters or (
                _utc(story.released_at or story.first_seen_at)
                - _utc(clusters[-1][0].released_at or clusters[-1][0].first_seen_at)
                > timedelta(days=7)
            ):
                clusters.append([])
            clusters[-1].append(story)
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            survivor = min(
                cluster,
                key=lambda story: (
                    _utc(story.released_at)
                    if story.released_at
                    else datetime.max.replace(tzinfo=timezone.utc),
                    _utc(story.first_seen_at),
                    story.id,
                ),
            )
            source_ids = {
                link.source_item_id
                for story in cluster
                for link in db.query(NewsStorySource).filter_by(story_id=story.id)
            }
            dated_sources = [
                source
                for source in db.query(NewsSourceItem).filter(NewsSourceItem.id.in_(source_ids))
                if source.published_at
            ]
            earliest_source = earliest_release(dated_sources)
            plans.append(
                MergePlan(
                    survivor.id,
                    tuple(sorted(story.id for story in cluster if story.id != survivor.id)),
                    tuple(sorted(source_ids)),
                    _utc(earliest_source.published_at) if earliest_source else None,
                    earliest_source.published_date_precision if earliest_source else None,
                )
            )
    return sorted(plans, key=lambda plan: plan.survivor_id)


def apply_analyst_merges(db: Session, plans: list[MergePlan], now: datetime) -> int:
    """Keep old rows for audit; only the survivor remains visible to the UI."""
    merged = 0
    for plan in plans:
        survivor = db.get(NewsStory, plan.survivor_id)
        if survivor is None or survivor.status not in {"ready", "pending"}:
            continue
        linked = {row.source_item_id for row in db.query(NewsStorySource).filter_by(story_id=survivor.id)}
        for source_id in plan.source_ids:
            if source_id not in linked:
                db.add(NewsStorySource(story_id=survivor.id, source_item_id=source_id))
        stock_ids = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=survivor.id)}
        for duplicate_id in plan.duplicate_ids:
            duplicate = db.get(NewsStory, duplicate_id)
            if duplicate is None or duplicate.status not in {"ready", "pending"}:
                continue
            for stock in db.query(NewsStoryStock).filter_by(story_id=duplicate_id):
                if stock.alpaca_asset_id not in stock_ids:
                    db.add(NewsStoryStock(story_id=survivor.id, alpaca_asset_id=stock.alpaca_asset_id))
                    stock_ids.add(stock.alpaca_asset_id)
            survivor.first_seen_at = min(_utc(survivor.first_seen_at), _utc(duplicate.first_seen_at))
            duplicate.status = "merged"
            duplicate.merged_into_story_id = survivor.id
            db.query(NewsEventIdentity).filter_by(story_id=duplicate.id).update({"story_id": survivor.id})
            db.query(NewsStory).filter_by(merged_into_story_id=duplicate.id).update(
                {"merged_into_story_id": survivor.id}
            )
            merged += 1
        if plan.released_at and _better_release_date(
            plan.released_at,
            plan.released_date_precision,
            survivor.released_at,
            survivor.released_date_precision,
        ):
            survivor.released_at = plan.released_at
            survivor.released_date_precision = plan.released_date_precision
        if survivor.event_date is None:
            event_dates = [
                source.event_date
                for source in db.query(NewsSourceItem).filter(NewsSourceItem.id.in_(plan.source_ids))
                if source.event_date
            ]
            if event_dates:
                survivor.event_date = min(event_dates)
        survivor.updated_at = now
        survivor.summary_dirty = True
    db.commit()
    return merged


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Preview or apply conservative news merges")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        pending = plan_analyst_merges(session)
        for plan in pending:
            print(
                f"survivor={plan.survivor_id} duplicates={plan.duplicate_ids} "
                f"sources={len(plan.source_ids)} released_at={plan.released_at}"
            )
        if args.apply:
            print(f"merged={apply_analyst_merges(session, pending, datetime.now(timezone.utc))}")
