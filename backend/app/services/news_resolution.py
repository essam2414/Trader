"""Resolve source-backed developments before publishing them, independently of feed cadence.

Identity is about the announcement, not the article or its generated category. Partial
identities may join one compatible event in its reporting window, never bridge conflicting
quarters/projects. Uncertain paraphrases must pass the semantic publication check.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from ..models import (
    NewsEventIdentity,
    NewsResolutionDecision,
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsStoryStock,
    WatchlistEntry,
)
from .news_dates import earliest_release, utc
from .news_identity import analyst_event_key, analyst_target_action_key
from .news_sources import SourceItem

if TYPE_CHECKING:
    from .news_ai import OpenAINewsAnalyser

IDENTITY_VERSION = 1
ACTIVE = ("ready", "pending", "resolving")
COVERED = (*ACTIVE, "expired")
_QUARTER = re.compile(r"\bq([1-4])\b|\b(first|second|third|fourth)[ -]quarter\b", re.I)
_PREVIEW = re.compile(
    r"\b(?:ahead of|upcoming|to report|due to report|expected to report|preview|"
    r"heads into|set to report|when it reports|could report|may report)\b",
    re.I,
)
_RESULT = re.compile(
    r"\b(?:report(?:s|ed)?|post(?:s|ed)?|deliver(?:s|ed)?|announce(?:s|d)?|"
    r"beat\w*|top\w*|hit a record)\b",
    re.I,
)
_REVISION = re.compile(r"\b(?:restat\w*|revis\w*|correct\w*|withdraw\w*|cancel\w*)\b", re.I)
_CAPACITY_ACTOR = re.compile(
    r"\b([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,2})\s+"
    r"(?:(?:said|announced|reportedly)\s+)?(?:plans?\s+to|wants?\s+to|will|is planning to)\s+"
    r"(?:double|triple|expand|increase|boost)\b"
)
_PRODUCTS = {
    "hdd": r"\b(?:hdd|hard[ -]disk[ -]drives?)\b",
    "nand": r"\bnand\b",
    "dram": r"\bdram\b",
    "hbm": r"\bhbm\b",
    "battery": r"\bbatter(?:y|ies)\b",
    "wafer": r"\bwafers?\b",
}


def source_item(source: NewsSourceItem) -> SourceItem:
    return SourceItem(
        source.provider,
        source.source_key,
        source.url,
        source.title,
        source.excerpt,
        source.published_at,
        tuple(source.candidate_symbols),
        source.date_status,
        source.published_date_precision or "minute",
        source.event_date,
    )


def describe(item: SourceItem, assets: list[WatchlistEntry], *, kind: str | None = None) -> dict:
    """Extract only explicit anchors; never infer a fiscal year from a publication year."""
    text = f"{item.title}. {item.excerpt}"
    if _REVISION.search(item.title):
        return {}
    for asset in assets if kind in {None, "analyst"} else []:
        target = analyst_target_action_key(item, asset)
        initiation = analyst_event_key(item, asset)
        # Analyst actions are independent developments even when they cite results.
        if target or initiation:
            parts = target or initiation
            return dict(
                kind="analyst",
                subject=asset.alpaca_asset_id,
                phase="action",
                anchors={"action": list(parts[1:])},
            )

    for match in _CAPACITY_ACTOR.finditer(text) if kind in {None, "capacity"} else []:
        passage = text[match.start() : match.end() + 800]
        product = next(
            (name for name, pattern in _PRODUCTS.items() if re.search(pattern, passage, re.I)), None
        )
        if not product or not re.search(r"\b(?:capacity|production|supply)\b", passage, re.I):
            continue
        anchors = {"product": product}
        year = re.search(r"\b(?:by|in|through)\s+(?:fiscal\s+)?(20\d{2})\b", passage, re.I)
        if year:
            anchors["target_year"] = year.group(1)
        location = re.search(
            r"\b(?:facilit\w*|plant|factory|project)\s+in\s+(?:the\s+)?"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            passage,
        )
        if location:
            anchors["location"] = location.group(1).lower()
        multiplier = re.search(r"\b(double|triple)\b", passage, re.I)
        if multiplier:
            anchors["scale"] = multiplier.group(1).lower()
        return dict(kind="capacity", subject=match.group(1).lower(), phase="announcement", anchors=anchors)

    if kind not in {None, "earnings"}:
        return {}
    # Do not mistake background earnings in an article about a different catalyst for its subject.
    if (
        kind is None
        and re.search(
            r"\b(?:strike|union|lawsuit|complaint|investigation|patent|acquir\w*|merger|"
            r"launch|unveil\w*|price target|target to|initiates?|upgrad\w*|downgrad\w*|"
            r"dividend|buyback|offering|bonus\w*|employee\w*|contract\w*|commitment\w*)\b",
            item.title,
            re.I,
        )
        and not re.search(r"\b(?:results|earnings|q[1-4])\b", item.title, re.I)
    ):
        return {}
    earnings = []
    for asset in assets:
        name = re.escape(asset.name.split()[0])
        mentions = list(re.finditer(rf"\b(?:{name}|{re.escape(asset.symbol)})\b", text, re.I))
        for mention in mentions:
            # Keep the evidence local to the issuer in a multi-company roundup.
            sentences = re.split(
                r"(?<!Inc)(?<!Corp)(?<!Adj)(?<!Co)\.\s+(?=[A-Z])", text[mention.start() : mention.end() + 700]
            )
            passage = sentences[0]
            for sentence in sentences[1:3]:
                if not re.match(
                    r"(?:Fiscal|Quarterly|Revenue|Adjusted earnings|EPS|It |Its |The company )", sentence
                ):
                    break
                passage += ". " + sentence
            if not re.search(r"\b(?:earnings|results|revenue|eps|q[1-4])\b", passage, re.I):
                continue
            if _REVISION.search(passage):
                continue  # A revision requires a separately dated, evidence-backed comparison.
            quarter = _QUARTER.search(passage)
            phase = "preview" if _PREVIEW.search(passage[:180]) else "results"
            if phase == "results" and not _RESULT.search(passage):
                continue
            anchors = {}
            if quarter:
                anchors["quarter"] = quarter.group(1) or str(
                    ("first", "second", "third", "fourth").index(quarter.group(2).lower()) + 1
                )
                # Bind the year to this quarter, not a later outlook or comparison year.
                year = re.match(
                    r"(?:\s+(?:of|fiscal|year|and|full.year)){0,4}\s+(20\d{2})\b",
                    passage[quarter.end() :],
                    re.I,
                )
                prior_year = re.search(
                    r"\b(?:fy|fiscal(?:\s+year)?)\s*(20\d{2})\s*$", passage[: quarter.start()], re.I
                )
                if year or prior_year:
                    anchors["fiscal_year"] = (year or prior_year).group(1)
            earnings.append(
                dict(kind="earnings", subject=asset.alpaca_asset_id, phase=phase, anchors=anchors)
            )
    subjects = {value["subject"] for value in earnings}
    if len(subjects) == 1:
        return max(earnings, key=lambda value: len(value["anchors"]))
    return {}


def identity_key(descriptor: dict) -> str | None:
    anchors = descriptor.get("anchors", {})
    if descriptor.get("kind") == "earnings" and {"quarter", "fiscal_year"} <= anchors.keys():
        return "earnings:" + ":".join(
            [descriptor["subject"], descriptor["phase"], anchors["fiscal_year"], anchors["quarter"]]
        )
    if (
        descriptor.get("kind") == "capacity"
        and {"product", "target_year", "location", "scale"} <= anchors.keys()
    ):
        return "capacity:" + hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()
    return None


def compatible(left: dict, right: dict, left_time: datetime | None, right_time: datetime | None) -> bool:
    if not left or not right or any(left.get(k) != right.get(k) for k in ("kind", "subject", "phase")):
        return False
    one, two = left.get("anchors", {}), right.get("anchors", {})
    if any(one[key] != two[key] for key in one.keys() & two.keys()):
        return False
    if identity_key(left) and identity_key(left) == identity_key(right):
        return True
    # Missing qualifiers may attach in a reporting window; discovery time is never the window.
    if left.get("kind") == "analyst" and (left_time is None or right_time is None):
        return False
    return bool(left_time and right_time and abs(utc(left_time) - utc(right_time)) <= timedelta(days=7))


def enrich(left: dict, right: dict) -> dict:
    if not left:
        return right
    return {**left, "anchors": {**left.get("anchors", {}), **right.get("anchors", {})}}


def sources_for(db: Session, story: NewsStory) -> list[NewsSourceItem]:
    return db.query(NewsSourceItem).join(NewsStorySource).filter(NewsStorySource.story_id == story.id).all()


def descriptor_for(db: Session, story: NewsStory, assets: list[WatchlistEntry]) -> dict:
    if story.event_descriptor:
        return story.event_descriptor
    stock_ids = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)}
    assets = [asset for asset in assets if asset.alpaca_asset_id in stock_ids]
    if story.status == "ready" and not re.search(
        r"\b(?:earnings|results|quarter|q[1-4]|eps|revenue)\b", story.headline, re.I
    ):
        # A generated card about another catalyst may quote results as background.
        focus_kind = "capacity" if _CAPACITY_ACTOR.search(story.headline) else "analyst"
    else:
        focus_kind = None
    focus = describe(
        SourceItem(
            "card",
            str(story.id),
            "https://local.invalid",
            story.headline,
            story.short_summary,
            story.released_at,
        ),
        assets,
        kind=focus_kind,
    )
    if story.status == "ready" and not focus:
        return {}
    if focus.get("kind") == "earnings":
        assets = [asset for asset in assets if asset.alpaca_asset_id == focus["subject"]]
    candidates = [
        describe(source_item(source), assets, kind=focus.get("kind")) for source in sources_for(db, story)
    ]
    if focus:
        candidates = [
            value
            for value in candidates
            if value and all(value.get(k) == focus.get(k) for k in ("kind", "subject", "phase"))
        ]
    candidates = [value for value in candidates if value]
    if not candidates:
        return {}
    best = max(candidates, key=lambda value: len(value.get("anchors", {})))
    # A story containing conflicting developments is not safe for deterministic consolidation.
    if any(any(value.get(k) != best.get(k) for k in ("kind", "subject", "phase")) for value in candidates):
        return {}
    for value in candidates:
        if any(
            value["anchors"][key] != best["anchors"][key]
            for key in value["anchors"].keys() & best["anchors"].keys()
        ):
            return {}
    return best


def find_development(
    db: Session, item: SourceItem, assets: list[WatchlistEntry]
) -> tuple[NewsStory | None, dict, bool]:
    descriptor = describe(item, assets)
    key = identity_key(descriptor)
    alias = db.get(NewsEventIdentity, key) if key else None
    if alias:
        return db.get(NewsStory, alias.story_id), descriptor, False
    if not descriptor:
        return None, {}, False
    matches = []
    # Industry subjects can affect different watchlist stocks. Their identity is global.
    query = db.query(NewsStory).filter(NewsStory.status.in_(COVERED))
    if descriptor["kind"] != "capacity":
        query = (
            query.join(NewsStoryStock)
            .filter(NewsStoryStock.alpaca_asset_id.in_([entry.alpaca_asset_id for entry in assets]))
            .distinct()
        )
    for story in query.order_by(NewsStory.id):
        other = descriptor_for(db, story, assets)
        if compatible(descriptor, other, item.published_at, story.released_at):
            matches.append(story)
    return (matches[0] if len(matches) == 1 else None), descriptor, len(matches) > 1


def remember(db: Session, story: NewsStory, descriptor: dict) -> None:
    story.event_descriptor = (
        enrich(story.event_descriptor or {}, descriptor) if descriptor else story.event_descriptor
    )
    story.identity_version = IDENTITY_VERSION
    key = identity_key(story.event_descriptor or {})
    if key and db.get(NewsEventIdentity, key) is None:
        db.add(NewsEventIdentity(event_key=key, story_id=story.id))
        db.flush()  # Unique primary key is the last line of defence against concurrent publication.


def record_decision(
    db: Session,
    story: NewsStory,
    outcome: str,
    reason: str,
    now: datetime,
    matched_story_id: int | None = None,
) -> None:
    hashes = sorted(source.content_hash for source in sources_for(db, story))
    digest = hashlib.sha256(json.dumps(hashes).encode()).hexdigest()
    previous = (
        db.query(NewsResolutionDecision)
        .filter_by(
            story_id=story.id,
            evidence_hash=digest,
            outcome=outcome,
            matched_story_id=matched_story_id,
            version=IDENTITY_VERSION,
        )
        .first()
    )
    if not previous:
        db.add(
            NewsResolutionDecision(
                story_id=story.id,
                matched_story_id=matched_story_id,
                outcome=outcome,
                reason=reason,
                evidence_hash=digest,
                version=IDENTITY_VERSION,
                created_at=now,
            )
        )


def correct_release(db: Session, story: NewsStory) -> bool:
    source = earliest_release(sources_for(db, story))
    if source and (
        story.released_at is None
        or utc(story.released_at) != utc(source.published_at)
        or story.released_date_precision != source.published_date_precision
    ):
        story.released_at = source.published_at
        story.released_date_precision = source.published_date_precision
        return True
    return False


def check_publication(db: Session, story: NewsStory, analyser: "OpenAINewsAnalyser", now: datetime) -> bool:
    """Compare all relevant stored history in bounded batches; missing comparison means hold.

    The candidate pool has no age cutoff. Batching bounds each request, not the history.
    Newer unresolved rows cannot block the oldest candidate forever.
    """
    if story.status != "resolving":
        return True
    assets = [row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=story.id)]
    history = (
        db.query(NewsStory)
        .join(NewsStoryStock)
        .filter(
            NewsStoryStock.alpaca_asset_id.in_(assets),
            NewsStory.id != story.id,
            (NewsStory.status.in_(("ready", "pending", "expired")))
            | ((NewsStory.status == "resolving") & (NewsStory.id < story.id)),
        )
        .distinct()
        .order_by(NewsStory.id)
        .all()
    )
    if not history:
        record_decision(db, story, "new", "No previously covered development for these stocks", now)
        return True
    compare = getattr(analyser, "compare_developments", None)
    if compare is None:
        record_decision(db, story, "unresolved", "Novelty comparison unavailable", now)
        return False

    def context(candidate: NewsStory) -> dict:
        evidence = "\n".join(f"{source.title}\n{source.excerpt}" for source in sources_for(db, candidate))
        return {
            "id": candidate.id,
            "headline": candidate.headline,
            "facts": candidate.key_facts,
            "descriptor": candidate.event_descriptor,
            "releasedAt": candidate.released_at.isoformat() if candidate.released_at else None,
            "evidence": evidence[:24000],
            "evidenceTruncated": len(evidence) > 24000,
        }

    incoming = context(story)
    # Budget reservations use their own transaction; release local writes before external calls.
    db.commit()
    matches = []
    for start in range(0, len(history), 12):
        decision = compare(incoming, [context(other) for other in history[start : start + 12]])
        if decision is None or decision.outcome == "unresolved":
            record_decision(db, story, "unresolved", "Novelty check incomplete or ambiguous", now)
            return False
        if decision.outcome != "new":
            matches.append(decision)
    if len(matches) > 1:
        record_decision(db, story, "unresolved", "Multiple prior developments match", now)
        return False
    if not matches:
        record_decision(db, story, "new", "Distinct from previously covered developments", now)
        return True
    decision = matches[0]
    prior = db.get(NewsStory, decision.matchedStoryId)
    if prior is None or prior.id == story.id or prior.status not in COVERED:
        return False
    record_decision(
        db,
        story,
        decision.outcome,
        f"{decision.reason}\nIncoming evidence: {decision.supportingQuote}\n"
        f"Previously covered: {decision.priorQuote}",
        now,
        prior.id,
    )
    if decision.outcome == "additional_coverage":
        merge_development(db, prior, story, now)
        return False
    story.related_story_id = prior.id
    return True


def merge_development(db: Session, survivor: NewsStory, duplicate: NewsStory, now: datetime) -> None:
    """Transfer provenance and aliases atomically; never delete audit history or revive merged cards."""
    if duplicate.id == survivor.id or duplicate.status == "merged":
        return
    source_ids = {source.id for source in sources_for(db, survivor)}
    for source in sources_for(db, duplicate):
        if source.id not in source_ids:
            db.add(NewsStorySource(story_id=survivor.id, source_item_id=source.id))
    stocks = {row.alpaca_asset_id for row in db.query(NewsStoryStock).filter_by(story_id=survivor.id)}
    for row in db.query(NewsStoryStock).filter_by(story_id=duplicate.id):
        if row.alpaca_asset_id not in stocks:
            db.add(NewsStoryStock(story_id=survivor.id, alpaca_asset_id=row.alpaca_asset_id))
    db.query(NewsEventIdentity).filter_by(story_id=duplicate.id).update({"story_id": survivor.id})
    db.query(NewsStory).filter_by(merged_into_story_id=duplicate.id).update(
        {"merged_into_story_id": survivor.id}
    )
    duplicate.status = "merged"
    duplicate.merged_into_story_id = survivor.id
    survivor.first_seen_at = min(utc(survivor.first_seen_at), utc(duplicate.first_seen_at))
    survivor.summary_dirty = survivor.status != "expired"
    survivor.updated_at = now
    db.flush()
    correct_release(db, survivor)
    record_decision(db, duplicate, "additional_coverage", "Same source-backed development", now, survivor.id)


def reconcile_developments(db: Session, now: datetime, *, apply: bool = False) -> dict:
    """Preview/repair using the same descriptors as ingestion. Preview performs no writes."""
    entries = db.query(WatchlistEntry).all()
    groups: list[tuple[NewsStory, dict]] = []
    merges, dates, held = [], [], []
    stories = db.query(NewsStory).filter(NewsStory.status.in_(ACTIVE)).order_by(NewsStory.id).all()
    for story in stories:
        descriptor = descriptor_for(db, story, entries)
        if story.status == "pending" and not story.identity_version and not descriptor:
            held.append(story.id)
            if apply:
                story.status = "resolving"
                record_decision(db, story, "unresolved", "Legacy candidate requires a novelty check", now)
        matches = [
            (other, desc)
            for other, desc in groups
            if compatible(descriptor, desc, story.released_at, other.released_at)
        ]
        # A fully qualified key also matches undated primary releases.
        key = identity_key(descriptor)
        if key:
            matches = [(other, desc) for other, desc in groups if identity_key(desc) == key] or matches
        if len(matches) == 1:
            survivor, prior = matches[0]
            merges.append({"survivor": survivor.id, "duplicate": story.id})
            combined = enrich(prior, descriptor)
            groups = [(other, combined if other.id == survivor.id else desc) for other, desc in groups]
            if apply:
                merge_development(db, survivor, story, now)
                remember(db, survivor, combined)
        else:
            groups.append((story, descriptor))
            if apply and descriptor:
                remember(db, story, descriptor)
        source = earliest_release(sources_for(db, story))
        if source and (
            story.released_at is None
            or utc(story.released_at) != utc(source.published_at)
            or story.released_date_precision != source.published_date_precision
        ):
            dates.append(story.id)
            if apply:
                correct_release(db, story)
    if apply:
        db.flush()
    return {"merges": merges, "corrected_dates": dates, "held_for_review": held}


if __name__ == "__main__":
    import argparse
    from datetime import timezone

    from ..db import SessionLocal

    parser = argparse.ArgumentParser(description="Preview or apply source-backed development repairs")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        report = reconcile_developments(session, datetime.now(timezone.utc), apply=args.apply)
        if args.apply:
            session.commit()
        print(json.dumps(report, indent=2))
