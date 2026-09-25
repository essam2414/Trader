"""Grouping, provenance, and fallback behavior for catalyst stories."""

from datetime import datetime, timezone

from app.models import NewsSourceItem, NewsStory, NewsStorySource, WatchlistEntry
from app.services.news_ai import ModelAnalysis
from app.services.news_digest import ingest_items, retry_pending
from app.services.news_sources import SourceItem, canonical_url


class FakeAnalyser:
    model = "fake-model"

    def analyse(self, entries, evidence, exposures):
        return ModelAnalysis(
            relevant=True,
            affectedAssetIds=[entries[0].alpaca_asset_id],
            category="deal",
            direction="upside",
            headline="Acme wins major contract",
            shortSummary="Acme announced a major contract.",
            detailSummary="Acme announced a major contract. The source does not disclose its value.",
            keyFacts=["Acme announced a contract."],
            unknowns=["Contract value was not disclosed."],
            relevanceReason="Acme is in the watchlist.",
            supportingSourceIds=[item.item_id for item in evidence],
        )


class FailedAnalyser:
    model = "unavailable"

    def analyse(self, entries, evidence, exposures):
        return None


def test_cross_source_duplicates_become_one_story_and_keep_earliest_release(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    early = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    late = datetime(2026, 9, 24, 22, tzinfo=timezone.utc)
    first = SourceItem(
        "company",
        "release",
        "https://example.com/release?utm_source=email",
        "Acme wins major contract",
        "Acme announced a major contract.",
        early,
        ("ACME",),
    )
    second = SourceItem(
        "alpaca",
        "article-5",
        "https://example.org/article",
        "Acme wins major contract",
        "Acme announced a major contract.",
        late,
        ("ACME",),
    )

    assert ingest_items(db_session, [first, second], [entry], FakeAnalyser(), late) == 2
    assert db_session.query(NewsStory).count() == 1
    story = db_session.query(NewsStory).one()
    assert story.released_at.replace(tzinfo=timezone.utc) == early
    assert story.status == "ready"
    assert db_session.query(NewsStorySource).count() == 2

    ingest_items(db_session, [first, second], [entry], FakeAnalyser(), late)
    assert db_session.query(NewsStory).count() == 1
    assert db_session.query(NewsSourceItem).count() == 2


def test_model_outage_preserves_direct_source_as_pending(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    item = SourceItem(
        "company",
        "a",
        "https://example.com/a",
        "Acme issues guidance",
        "Acme issued guidance.",
        now,
        ("ACME",),
    )
    ingest_items(db_session, [item], [entry], FailedAnalyser(), now)
    story = db_session.query(NewsStory).one()
    assert story.status == "pending"
    assert story.detail_summary == ""
    assert story.headline == item.title

    assert retry_pending(db_session, [entry], FakeAnalyser(), now, [1]) == 1
    assert story.status == "ready"


def test_tracking_parameters_do_not_change_canonical_url():
    assert canonical_url("https://Example.com/story/?utm_source=mail&fbclid=x") == "https://example.com/story"


def test_separate_contract_values_do_not_merge_into_one_story(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    items = [
        SourceItem(
            "company",
            "one",
            "https://example.com/one",
            "Acme wins $2 billion contract",
            "Acme won a $2 billion contract.",
            now,
            ("ACME",),
        ),
        SourceItem(
            "company",
            "two",
            "https://example.com/two",
            "Acme wins $3 billion contract",
            "Acme won a $3 billion contract.",
            now,
            ("ACME",),
        ),
    ]
    ingest_items(db_session, items, [entry], FailedAnalyser(), now)
    assert db_session.query(NewsStory).count() == 2
