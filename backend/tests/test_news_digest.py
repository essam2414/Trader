"""Grouping, provenance, and fallback behavior for catalyst stories."""

from datetime import datetime, timezone

from app.models import NewsSourceItem, NewsStory, NewsStorySource, WatchlistEntry
from app.services import news_digest
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


def test_scheduled_collection_summarises_cluster_once_after_all_sources_arrive(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    items = [
        SourceItem("ir_acme", "one", "https://example.com/one", "Acme wins contract", "", now, ("ACME",)),
        SourceItem("alpaca", "two", "https://example.com/two", "Acme wins contract", "", now, ("ACME",)),
    ]

    class CountingAnalyser(FakeAnalyser):
        evidence_counts = []

        def analyse(self, entries, evidence, exposures):
            self.evidence_counts.append(len(evidence))
            return super().analyse(entries, evidence, exposures)

    analyser = CountingAnalyser()
    assert ingest_items(db_session, items, [entry], analyser, now, [0]) == 2
    assert analyser.evidence_counts == []
    assert db_session.query(NewsStory).one().status == "pending"
    assert retry_pending(db_session, [entry], analyser, now, [20]) == 1
    assert analyser.evidence_counts == [2]


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


def test_dilution_and_insider_sale_headlines_reach_analysis(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    items = [
        SourceItem(
            "publisher",
            "dilution",
            "https://example.com/dilution",
            "Acme Corp warns of dilution",
            "Acme Corp warns of dilution.",
            now,
            ("ACME",),
        ),
        SourceItem(
            "sec",
            "sale",
            "https://example.com/sale",
            "Acme Corp filed Form 4 reporting an insider sale",
            "Form 4 reports sale transaction code S.",
            now,
            ("ACME",),
        ),
        SourceItem(
            "sec",
            "shelf",
            "https://example.com/shelf",
            "Acme Corp filed Form S-3ASR",
            "Automatic shelf registration statement.",
            now,
            ("ACME",),
        ),
    ]
    assert ingest_items(db_session, items, [entry], FailedAnalyser(), now) == 3
    assert db_session.query(NewsStory).count() == 3
    assert {story.category for story in db_session.query(NewsStory)} == {"financing", "insider"}


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


def test_sync_analyzes_more_than_twenty_pending_stories(db_session, monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    items = [
        SourceItem(
            "company",
            str(number),
            f"https://example.com/{number}",
            f"Acme wins ${number} million contract",
            "Acme announced a contract.",
            now,
            ("ACME",),
        )
        for number in range(1, 22)
    ]
    assert ingest_items(db_session, items, [entry], FailedAnalyser(), now, [0]) == 21
    assert db_session.query(NewsStory).filter_by(status="pending").count() == 21
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in (
        "sec_items",
        "spglobal_index_items",
        "alpaca_items",
        "gdelt_items",
        "gdelt_exposure_items",
    ):
        monkeypatch.setattr(news_digest, source, lambda *args: [])

    result = news_digest.run_news_sync(db_session, FakeAnalyser(), now, http=object())
    assert result["pending_retried"] == 21
    assert db_session.query(NewsStory).filter_by(status="ready").count() == 21
