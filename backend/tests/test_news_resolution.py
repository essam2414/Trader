"""Real repeated developments must be resolved before they reach the dashboard."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models import NewsResolutionDecision, NewsSourceItem, NewsStory, NewsStorySource, WatchlistEntry
from app.services.news_digest import ingest_items, retry_pending
from app.services.news_novelty import NoveltyDecision
from app.services.news_resolution import reconcile_developments
from app.services.news_sources import SourceItem

NOW = datetime(2026, 10, 3, 18, tzinfo=timezone.utc)


class UnavailableAnalyser:
    model = "unavailable"

    def analyse(self, *args, **kwargs):
        return None


def fixtures(group):
    rows = json.loads((Path(__file__).parent / "fixtures/news_duplicate_developments.json").read_text())
    return [
        SourceItem(
            row["provider"],
            row["key"],
            row["url"],
            row["title"],
            row["excerpt"],
            datetime.fromisoformat(row["published_at"]).replace(tzinfo=timezone.utc)
            if row["published_at"]
            else None,
            tuple(row["symbols"]),
        )
        for row in rows
        if row["group"] == group
    ]


def stock(db, symbol="WDC", name="Western Digital"):
    entry = WatchlistEntry(alpaca_asset_id=f"asset-{symbol}", symbol=symbol, name=name, exchange="NASDAQ")
    db.add(entry)
    db.commit()
    return entry


@pytest.mark.parametrize(
    "group,symbol,name", [("capacity", "WDC", "Western Digital"), ("results", "MU", "Micron Technology")]
)
@pytest.mark.parametrize("reverse", [False, True])
def test_real_development_has_one_card_across_refreshes(db_session, group, symbol, name, reverse):
    entry = stock(db_session, symbol, name)
    items = fixtures(group)
    if reverse:
        items.reverse()
    for index, item in enumerate(items):
        ingest_items(db_session, [item], [entry], UnavailableAnalyser(), NOW + timedelta(days=index * 8))
    visible = db_session.query(NewsStory).filter(NewsStory.status.in_(["ready", "pending"])).all()
    assert len(visible) == 1
    assert db_session.query(NewsStorySource).filter_by(story_id=visible[0].id).count() == len(items)
    assert visible[0].released_at.replace(tzinfo=timezone.utc) == min(
        item.published_at for item in items if item.published_at
    )
    before = db_session.query(NewsStory).count()
    ingest_items(db_session, items, [entry], UnavailableAnalyser(), NOW + timedelta(days=90))
    assert db_session.query(NewsStory).count() == before
    assert db_session.query(NewsSourceItem).count() == len(items)


def test_earlier_same_day_source_corrects_release_time(db_session):
    entry = stock(db_session)
    late = SourceItem(
        "publisher",
        "late",
        "https://example.com/late",
        "Western Digital wins contract",
        "Western Digital announced a supply contract.",
        NOW,
        ("WDC",),
    )
    early = SourceItem(
        "publisher",
        "early",
        "https://example.com/early",
        late.title,
        late.excerpt,
        NOW - timedelta(hours=4),
        ("WDC",),
    )
    ingest_items(db_session, [late, early], [entry], UnavailableAnalyser(), NOW)
    story = db_session.query(NewsStory).one()
    assert story.released_at.replace(tzinfo=timezone.utc) == early.published_at


def article(key, title, excerpt="", when=NOW, symbol="MU"):
    return SourceItem("publisher", key, f"https://example.com/{key}", title, excerpt, when, (symbol,))


@pytest.mark.parametrize(
    "title",
    [
        "Micron reports fiscal fourth-quarter 2025 results",
        "Micron reports fiscal third-quarter 2026 results",
        "Micron previews upcoming fiscal fourth-quarter 2026 results",
        "Micron revises fiscal fourth-quarter 2026 results",
        "Mizuho raises Micron price target to $1400 following earnings",
        "Micron workers threaten strike over bonuses",
    ],
)
def test_distinct_developments_do_not_merge_with_results(db_session, title):
    entry = stock(db_session, "MU", "Micron")
    base = article("results", "Micron reports fiscal fourth-quarter 2026 results")
    other = article("other", title, "Micron previously reported fiscal fourth-quarter 2026 results.")
    ingest_items(db_session, [base, other], [entry], UnavailableAnalyser(), NOW)
    assert db_session.query(NewsStory).filter(NewsStory.status != "merged").count() == 2


def test_capacity_projects_and_ambiguous_roundup_do_not_bridge(db_session):
    entry = stock(db_session)
    items = [
        article(str(index), title, symbol="WDC")
        for index, title in enumerate(
            [
                "Toshiba plans to double HDD production capacity at facilities "
                "in the Philippines by fiscal 2027",
                "Toshiba plans to double HDD production capacity at facilities in Japan by fiscal 2027",
                "Toshiba plans to double HDD production capacity for data centers",
            ]
        )
    ]
    ingest_items(db_session, items, [entry], UnavailableAnalyser(), NOW)
    assert db_session.query(NewsStory).filter(NewsStory.status != "merged").count() == 3
    assert db_session.query(NewsStory).filter_by(status="resolving").count() == 1


class ComparingAnalyser:
    model = "test"

    def __init__(self, outcome="additional_coverage"):
        self.outcome = outcome
        self.batches = []

    def analyse(self, entries, evidence, exposures):
        from app.services.news_ai import ModelAnalysis

        return ModelAnalysis(
            relevant=True,
            affectedAssetIds=[entries[0].alpaca_asset_id],
            category="deal",
            direction="unclear",
            headline=evidence[0].item.title,
            shortSummary="Source-backed development",
            detailSummary="Source-backed development",
            keyFacts=[],
            unknowns=[],
            relevanceReason="Watched stock",
            supportingSourceIds=[evidence[0].item_id],
        )

    def compare_developments(self, incoming, history):
        self.batches.append(history)
        return NoveltyDecision(
            outcome=self.outcome,
            matchedStoryId=history[0]["id"]
            if self.outcome in {"additional_coverage", "material_update"}
            else None,
            reason="Evidence comparison",
            supportingQuote=incoming["evidence"].splitlines()[0],
            priorQuote=history[0]["evidence"].split("\n")[0],
        )


def test_semantic_duplicate_is_hidden_then_attached_on_pending_retry(db_session):
    entry = stock(db_session, "MU", "Micron")
    first = article("a", "Micron announces a supply agreement", "Micron agrees to supply Acme.")
    recap = article(
        "b",
        "Acme secures memory supply deal",
        "Acme agreed to buy memory from Micron.",
        NOW + timedelta(days=30),
    )
    ingest_items(db_session, [first, recap], [entry], UnavailableAnalyser(), NOW)
    assert db_session.query(NewsStory).filter_by(status="pending").count() == 1
    assert db_session.query(NewsStory).filter_by(status="resolving").count() == 1
    analyser = ComparingAnalyser()
    retry_pending(db_session, [entry], analyser, NOW + timedelta(days=31), [10])
    survivor = db_session.query(NewsStory).filter_by(status="ready").one()
    assert survivor.released_at.replace(tzinfo=timezone.utc) == NOW
    assert db_session.query(NewsStorySource).filter_by(story_id=survivor.id).count() == 2
    assert db_session.query(NewsStory).filter_by(status="merged").count() == 1
    assert analyser.batches
    assert db_session.query(NewsResolutionDecision).filter_by(outcome="additional_coverage").count() > 0


def test_material_update_at_same_url_preserves_original_evidence_and_links_developments(db_session):
    entry = stock(db_session, "MU", "Micron")
    first = article("a", "Micron announces a supply agreement", "Micron agrees to supply Acme.")
    update = article(
        "a",
        "Micron cancels a supply agreement",
        "Micron cancelled the Acme agreement.",
        NOW + timedelta(days=2),
    )
    analyser = ComparingAnalyser("material_update")
    ingest_items(db_session, [first], [entry], analyser, NOW)
    ingest_items(db_session, [update], [entry], analyser, NOW + timedelta(days=2))
    stories = db_session.query(NewsStory).order_by(NewsStory.id).all()
    assert len(stories) == 2
    assert stories[1].related_story_id == stories[0].id
    assert stories[1].status == "ready"
    assert stories[1].released_at.replace(tzinfo=timezone.utc) == update.published_at
    assert db_session.query(NewsSourceItem).count() == 2
    assert db_session.query(NewsSourceItem).order_by(NewsSourceItem.id).first().excerpt == first.excerpt
    ingest_items(db_session, [update], [entry], analyser, NOW + timedelta(days=3))
    assert db_session.query(NewsStory).count() == 2


def test_unavailable_novelty_check_never_publishes_a_possible_duplicate(db_session):
    entry = stock(db_session, "MU", "Micron")
    ingest_items(
        db_session,
        [
            article("a", "Micron announces a supply agreement"),
            article("b", "Acme secures a semiconductor contract"),
        ],
        [entry],
        UnavailableAnalyser(),
        NOW,
    )
    analyser = ComparingAnalyser("unresolved")
    retry_pending(db_session, [entry], analyser, NOW, [10])
    assert db_session.query(NewsStory).filter_by(status="ready").count() == 1
    assert db_session.query(NewsStory).filter_by(status="resolving").count() == 1


def test_completed_comparison_batches_survive_retry_and_invalidate_on_evidence_change(db_session):
    from app.models import NewsStoryStock
    from app.services.news_resolution import check_publication

    entry = stock(db_session, "MU", "Micron")
    for index in range(14):
        row = NewsStory(
            headline=f"Micron event {index}",
            short_summary="",
            detail_summary="",
            relevance_reason="",
            key_facts=[],
            unknowns=[],
            category="deal",
            direction="unclear",
            status="ready" if index < 13 else "resolving",
            first_seen_at=NOW,
            updated_at=NOW,
        )
        db_session.add(row)
        db_session.flush()
        db_session.add(NewsStoryStock(story_id=row.id, alpaca_asset_id=entry.alpaca_asset_id))
        source = NewsSourceItem(
            provider="publisher",
            source_key=str(index),
            url=f"https://example.com/{index}",
            title=row.headline,
            excerpt="Source evidence",
            content_hash=str(index),
            first_seen_at=NOW,
        )
        db_session.add(source)
        db_session.flush()
        db_session.add(NewsStorySource(story_id=row.id, source_item_id=source.id))
    db_session.commit()
    candidate = row

    class PartialAnalyser(ComparingAnalyser):
        def compare_developments(self, incoming, history):
            if len(history) == 1:
                self.batches.append(history)
                self.last_failure_kind = "temporary"
                self.last_failure_reason = "Coverage comparison timed out"
                return None
            return super().compare_developments(incoming, history)

    analyser = PartialAnalyser("new")
    assert not check_publication(db_session, candidate, analyser, NOW)
    assert [len(batch) for batch in analyser.batches] == [12, 1]
    assert not check_publication(db_session, candidate, analyser, NOW)
    assert [len(batch) for batch in analyser.batches] == [12, 1, 1]
    first = db_session.query(NewsStory).order_by(NewsStory.id).first()
    first.headline = "Changed earlier evidence context"
    db_session.commit()
    assert not check_publication(db_session, candidate, analyser, NOW)
    assert [len(batch) for batch in analyser.batches] == [12, 1, 1, 12, 1]


def test_repair_is_idempotent_and_preview_is_read_only(db_session):
    entry = stock(db_session)
    # Simulate legacy rows by collecting independently and removing each identity during setup.
    from app.models import NewsEventIdentity, NewsStoryStock

    for index, item in enumerate(fixtures("capacity")):
        source = NewsSourceItem(
            provider=item.provider,
            source_key=item.key,
            url=item.url,
            title=item.title,
            excerpt=item.excerpt,
            candidate_symbols=["WDC"],
            published_at=item.published_at,
            first_seen_at=NOW,
            content_hash=str(index),
        )
        story = NewsStory(
            headline=item.title,
            status="pending",
            released_at=item.published_at,
            first_seen_at=NOW,
            updated_at=NOW,
        )
        db_session.add_all([source, story])
        db_session.flush()
        db_session.add_all(
            [
                NewsStorySource(story_id=story.id, source_item_id=source.id),
                NewsStoryStock(story_id=story.id, alpaca_asset_id=entry.alpaca_asset_id),
            ]
        )
    db_session.commit()
    preview = reconcile_developments(db_session, NOW)
    assert len(preview["merges"]) == 3
    assert not db_session.dirty and not db_session.new
    reconcile_developments(db_session, NOW, apply=True)
    db_session.commit()
    assert db_session.query(NewsStory).filter_by(status="pending").count() == 1
    assert db_session.query(NewsEventIdentity).count() >= 1
    assert reconcile_developments(db_session, NOW, apply=True)["merges"] == []


@pytest.mark.parametrize("reverse", [False, True])
def test_date_only_does_not_invent_a_midnight_release(db_session, reverse):
    from dataclasses import replace

    entry = stock(db_session, "MU", "Micron")
    precise = article("precise", "Micron reports fiscal fourth-quarter 2026 results")
    day = replace(
        precise,
        key="day",
        url="https://example.com/day",
        published_at=NOW.replace(hour=0),
        published_date_precision="date",
    )
    items = [day, precise] if reverse else [precise, day]
    ingest_items(db_session, items, [entry], UnavailableAnalyser(), NOW)
    story = db_session.query(NewsStory).one()
    assert story.released_date_precision == "minute"
    assert story.released_at.replace(tzinfo=timezone.utc) == NOW


def test_history_comparison_checks_every_batch_and_does_not_forget_older_events(db_session):
    from app.models import NewsStoryStock

    entry = stock(db_session, "MU", "Micron")
    for number in range(14):
        story = NewsStory(
            headline=f"Distinct contract {number}",
            status="ready",
            first_seen_at=NOW,
            released_at=NOW - timedelta(days=100 + number),
            updated_at=NOW,
        )
        db_session.add(story)
        db_session.flush()
        db_session.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=entry.alpaca_asset_id))
    db_session.commit()
    analyser = ComparingAnalyser("new")
    ingest_items(
        db_session, [article("later", "Micron announces new supply agreement")], [entry], analyser, NOW
    )
    assert [len(batch) for batch in analyser.batches] == [12, 2]


def test_pending_retry_excludes_merged_rows_and_uses_survivor_on_replay(db_session):
    entry = stock(db_session)
    items = fixtures("capacity")
    ingest_items(db_session, items, [entry], UnavailableAnalyser(), NOW)
    ids = [row.id for row in db_session.query(NewsStory).filter(NewsStory.status != "merged")]
    retry_pending(db_session, [entry], ComparingAnalyser(), NOW, [10])
    ingest_items(db_session, items, [entry], UnavailableAnalyser(), NOW + timedelta(days=30))
    assert [row.id for row in db_session.query(NewsStory).filter(NewsStory.status != "merged")] == ids


def test_archived_development_is_not_resurfaced_by_a_new_article(db_session):
    entry = stock(db_session, "MU", "Micron")
    ingest_items(
        db_session,
        [article("a", "Micron announces a supply agreement")],
        [entry],
        ComparingAnalyser("new"),
        NOW,
    )
    original = db_session.query(NewsStory).one()
    original.status = "expired"
    db_session.commit()
    ingest_items(
        db_session,
        [
            article(
                "b",
                "Acme secures a memory supply contract",
                "Acme agreed to buy memory from Micron.",
                NOW + timedelta(days=30),
            )
        ],
        [entry],
        ComparingAnalyser(),
        NOW + timedelta(days=30),
    )
    assert db_session.query(NewsStory).filter(NewsStory.status.in_(("ready", "pending"))).count() == 0
    assert original.status == "expired"


def test_archived_typed_identity_is_not_revived_by_late_coverage(db_session):
    entry = stock(db_session, "MU", "Micron")
    title = "Micron reports fiscal fourth-quarter 2026 results"
    ingest_items(db_session, [article("original", title)], [entry], UnavailableAnalyser(), NOW)
    original = db_session.query(NewsStory).one()
    original.status = "expired"
    db_session.commit()
    ingest_items(
        db_session,
        [article("recap", title, when=NOW + timedelta(days=30))],
        [entry],
        ComparingAnalyser("new"),
        NOW + timedelta(days=30),
    )
    assert db_session.query(NewsStory).count() == 1
    assert original.status == "expired"
