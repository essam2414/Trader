"""Grouping, provenance, and fallback behavior for catalyst stories."""

from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.db import Base
from app.models import (
    NewsAiDailyUsage,
    NewsCollectionRun,
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsSyncState,
    WatchlistEntry,
)
from app.services import news_digest
from app.services.news_ai import ModelAnalysis
from app.services.news_ai_budget import DailyNewsTokenBudget
from app.services.news_digest import ingest_items, retry_pending
from app.services.news_sources import SourceItem, canonical_url


class FakeAnalyser:
    model = "fake-model"

    def compare_developments(self, incoming, history):
        from app.services.news_novelty import NoveltyDecision

        return NoveltyDecision(
            outcome="new",
            matchedStoryId=None,
            reason="Distinct test contract",
            supportingQuote=incoming["evidence"].splitlines()[0],
            priorQuote="",
        )

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


def test_repeated_validation_is_held_until_evidence_changes_or_manual_retry(db_session):
    class RejectedAnalyser(FailedAnalyser):
        last_failure_kind = "validation"
        last_failure_reason = "Unsupported number: $99B"

    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    item = SourceItem("company", "a", "https://example.com/a", "Acme wins contract", "", now, ("ACME",))
    ingest_items(db_session, [item], [entry], RejectedAnalyser(), now, [0])
    story = db_session.query(NewsStory).one()
    for attempt in range(3):
        assert (
            retry_pending(db_session, [entry], RejectedAnalyser(), now + timedelta(hours=attempt), [1]) == 1
        )
    state = db_session.get(NewsSyncState, f"analysis:{story.id}")
    assert state.last_outcome == "needs_review"
    assert state.failure_count == 3
    assert state.next_attempt_at is None
    assert retry_pending(db_session, [entry], RejectedAnalyser(), now + timedelta(hours=4), [1]) == 0
    assert (
        retry_pending(db_session, [entry], RejectedAnalyser(), now + timedelta(hours=4), [1], force=True) == 1
    )
    source = db_session.query(NewsSourceItem).one()
    source.excerpt = "Acme disclosed new contract evidence."
    db_session.commit()
    assert retry_pending(db_session, [entry], RejectedAnalyser(), now + timedelta(hours=5), [1]) == 1
    assert state.failure_count == 1
    assert state.last_outcome == "failure"


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


def test_later_duplicate_source_keeps_ready_summary_when_analysis_is_deferred(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-a", symbol="AAAA", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    first = SourceItem(
        "publisher", "one", "https://example.com/one", "Acme wins contract", "", now, ("AAAA",)
    )
    second = SourceItem("alpaca", "two", "https://example.com/two", "Acme wins contract", "", now, ("AAAA",))

    ingest_items(db_session, [first], [entry], FakeAnalyser(), now)
    ingest_items(db_session, [second], [entry], FakeAnalyser(), now, [0])

    story = db_session.query(NewsStory).one()
    assert story.status == "ready"
    assert db_session.query(NewsStorySource).count() == 2


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


def test_pending_analysis_retries_independently_with_failure_cooldown(db_session, monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)
    item = SourceItem("company", "a", "https://example.com/a", "Acme wins contract", "", now, ("ACME",))
    ingest_items(db_session, [item], [entry], FailedAnalyser(), now, [0])
    story = db_session.query(NewsStory).one()

    assert retry_pending(db_session, [entry], FailedAnalyser(), now, [1]) == 1
    state = db_session.get(NewsSyncState, f"analysis:{story.id}")
    assert state.last_error == "Summary analysis did not complete"
    monkeypatch.setattr(FakeAnalyser, "model", FailedAnalyser.model)
    assert retry_pending(db_session, [entry], FakeAnalyser(), now + timedelta(minutes=1), [1]) == 0
    assert story.status == "pending"
    assert retry_pending(db_session, [entry], FakeAnalyser(), now + timedelta(minutes=5), [1]) == 1
    assert story.status == "ready"
    assert db_session.get(NewsSyncState, f"analysis:{story.id}") is None


def test_manual_pending_analysis_ignores_saved_failure_cooldown(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)
    item = SourceItem("company", "a", "https://example.com/a", "Acme wins contract", "", now, ("ACME",))
    ingest_items(db_session, [item], [entry], FailedAnalyser(), now, [0])
    assert retry_pending(db_session, [entry], FailedAnalyser(), now, [1]) == 1

    assert (
        retry_pending(db_session, [entry], FakeAnalyser(), now + timedelta(minutes=1), [1], force=True) == 1
    )
    assert db_session.query(NewsStory).one().status == "ready"


def test_pending_analysis_job_completes_stored_story_without_collecting_sources(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)
    item = SourceItem("company", "a", "https://example.com/a", "Acme wins contract", "", now, ("ACME",))
    ingest_items(db_session, [item], [entry], FailedAnalyser(), now, [0])

    class AvailableAnalyser(FakeAnalyser):
        def available(self):
            return True

    assert news_digest.run_pending_analysis(db_session, AvailableAnalyser()) == 1
    assert db_session.query(NewsStory).one().status == "ready"
    assert db_session.query(NewsSourceItem).count() == 1


def test_failed_reanalysis_preserves_existing_ready_summary(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 27, 15, tzinfo=timezone.utc)
    first = SourceItem("company", "a", "https://example.com/a", "Acme wins contract", "", now, ("ACME",))
    second = SourceItem("alpaca", "b", "https://example.com/b", "Acme wins contract", "", now, ("ACME",))
    ingest_items(db_session, [first], [entry], FakeAnalyser(), now)
    story = db_session.query(NewsStory).one()
    summary = story.detail_summary

    ingest_items(db_session, [second], [entry], FailedAnalyser(), now + timedelta(minutes=1))

    assert story.status == "ready"
    assert story.detail_summary == summary


def test_pending_story_with_competing_headline_signals_is_unclear(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)
    item = SourceItem(
        "company",
        "guidance",
        "https://example.com/guidance",
        "Acme raises guidance but cuts guidance",
        "Acme issued updated guidance.",
        now,
        ("ACME",),
    )

    assert ingest_items(db_session, [item], [entry], FailedAnalyser(), now) == 1
    story = db_session.query(NewsStory).one()
    assert story.status == "pending"
    assert story.direction == "unclear"


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


def test_analyst_initiation_without_price_target_reaches_ingestion(db_session):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)
    item = SourceItem(
        "publisher",
        "rosenblatt-sndk",
        "https://example.com/rosenblatt-sndk",
        "Rosenblatt starts coverage of Sandisk at Buy",
        "Analyst Kevin Cassidy initiates coverage with a Buy rating.",
        now,
        (),
    )

    assert ingest_items(db_session, [item], [entry], FailedAnalyser(), now) == 1
    assert db_session.query(NewsStory).one().category == "analyst"


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


def test_analyst_initiation_headlines_with_target_format_variants_merge(db_session):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 22, 16, tzinfo=timezone.utc)
    items = [
        SourceItem(
            "publisher",
            "mt",
            "https://example.com/mt",
            "Rosenblatt Initiates Sandisk at Buy With $2,400 Price Target",
            "",
            now,
            ("SNDK",),
        ),
        SourceItem(
            "alpaca",
            "benzinga",
            "https://example.com/benzinga",
            "Rosenblatt Initiates Coverage On SanDisk with Buy Rating, Announces Price Target of $2400",
            "",
            now,
            ("SNDK",),
        ),
    ]

    assert ingest_items(db_session, items, [entry], FailedAnalyser(), now) == 2
    assert db_session.query(NewsStory).count() == 1
    assert db_session.query(NewsStorySource).count() == 2
    other_firm = SourceItem(
        "publisher",
        "mizuho",
        "https://example.com/mizuho",
        "Mizuho Initiates Sandisk at Buy With $2,400 Price Target",
        "",
        now,
        ("SNDK",),
    )
    assert ingest_items(db_session, [other_firm], [entry], FailedAnalyser(), now) == 1
    assert db_session.query(NewsStory).count() == 2


def test_sandisk_rosenblatt_reports_form_one_dated_story(db_session):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    db_session.add(entry)
    db_session.commit()
    released = datetime(2026, 9, 22, 9, 15, tzinfo=timezone.utc)
    found = datetime(2026, 9, 27, 14, 27, tzinfo=timezone.utc)
    items = [
        SourceItem(
            "publisher_backfill",
            "original",
            "https://example.com/original",
            "Rosenblatt Initiates Sandisk at Buy With $2,400 Price Target",
            "",
            released,
            ("SNDK",),
        ),
        SourceItem(
            "alpaca",
            "roundup",
            "https://example.com/roundup",
            "This SanDisk Analyst Begins Coverage On A Bullish Note; Here Are Top 5 Initiations",
            "Rosenblatt analyst Kevin Cassidy initiated coverage on SanDisk Corp (NASDAQ: SNDK) "
            "with a Buy rating and announced a price target of $2,400.",
            datetime(2026, 9, 22, 12, 54, tzinfo=timezone.utc),
            ("SNDK",),
        ),
        SourceItem(
            "openai_web",
            "tipranks",
            "https://example.com/tipranks",
            "SanDisk Stock Price Forecast — Rosenblatt Analyst Sees 36% Upside",
            "Search-cited catalyst: Rosenblatt initiated SanDisk at Buy with a $2,400 "
            "price target on September 22, 2026.",
            None,
        ),
    ]

    assert ingest_items(db_session, items, [entry], FailedAnalyser(), found) == 3
    assert db_session.query(NewsStory).count() == 1
    assert db_session.query(NewsStorySource).count() == 3
    assert db_session.query(NewsStory).one().released_at.replace(tzinfo=timezone.utc) == released


def test_existing_source_gains_verified_publication_date(db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-a", symbol="AAAA", name="Acme Corp", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    found = datetime(2026, 9, 27, tzinfo=timezone.utc)
    old = SourceItem("web", "one", "https://example.com/one", "Acme wins contract", "", None, ("AAAA",))
    dated = SourceItem(
        "web",
        "one",
        old.url,
        old.title,
        old.excerpt,
        datetime(2026, 9, 22, tzinfo=timezone.utc),
        old.symbols,
    )

    ingest_items(db_session, [old], [entry], FailedAnalyser(), found)
    ingest_items(db_session, [dated], [entry], FailedAnalyser(), found)

    assert db_session.query(NewsSourceItem).one().published_at.date().isoformat() == "2026-09-22"
    assert db_session.query(NewsStory).one().released_at.date().isoformat() == "2026-09-22"


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
    assert db_session.query(NewsStory).filter(NewsStory.status.in_(("pending", "resolving"))).count() == 21
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in (
        "sec_items",
        "spglobal_index_items",
        "alpaca_items",
    ):
        monkeypatch.setattr(news_digest, source, lambda *args: [])

    result = news_digest.run_news_sync(db_session, FakeAnalyser(), now + timedelta(days=1), http=object())
    assert result["pending_retried"] == 21
    assert db_session.query(NewsStory).filter_by(status="ready").count() == 21
    assert db_session.query(NewsCollectionRun).one().new_card_count == 21


def test_web_search_fills_gap_when_other_sources_return_nothing(db_session, monkeypatch):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    db_session.add(entry)
    db_session.commit()
    now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in (
        "sec_items",
        "spglobal_index_items",
        "alpaca_items",
    ):
        monkeypatch.setattr(news_digest, source, lambda *args: [])

    class FakeWebDiscovery:
        def available(self):
            return True

        def search(self, stock, since, until, http):
            assert stock.symbol == "SNDK"
            return [
                SourceItem(
                    "openai_web",
                    "rosenblatt",
                    "https://example.com/sndk",
                    "A new chapter for Sandisk",
                    "Search-cited catalyst: Rosenblatt initiates coverage of Sandisk "
                    "at Buy with $2,400 target.",
                    now,
                )
            ]

    monkeypatch.setattr(news_digest, "OpenAIWebNewsDiscovery", FakeWebDiscovery)
    result = news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object())

    assert result["openai_web:SNDK"] == 1
    assert db_session.query(NewsSourceItem).one().provider == "openai_web"
    assert db_session.query(NewsStory).one().status == "pending"
    assert "Rosenblatt" in db_session.query(NewsStory).one().short_summary


def test_web_search_does_not_repeat_within_six_hours(db_session, monkeypatch):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    db_session.add_all(
        [
            entry,
            NewsSyncState(source_key="openai_web:SNDK", last_attempt_at=now - timedelta(hours=1)),
        ]
    )
    db_session.commit()
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in (
        "sec_items",
        "spglobal_index_items",
        "alpaca_items",
    ):
        monkeypatch.setattr(news_digest, source, lambda *args: [])

    class FakeWebDiscovery:
        def available(self):
            return True

        def search(self, *args):
            raise AssertionError("web search should be on cooldown")

    monkeypatch.setattr(news_digest, "OpenAIWebNewsDiscovery", FakeWebDiscovery)
    result = news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object())

    assert "openai_web:SNDK" not in result


def test_failed_web_search_retries_before_six_hours_then_uses_failure_cooldown(db_session, monkeypatch):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk Corporation", exchange="NASDAQ"
    )
    now = datetime(2026, 9, 27, 17, tzinfo=timezone.utc)
    db_session.add_all(
        [
            entry,
            NewsSyncState(
                source_key="openai_web:SNDK",
                last_attempt_at=now - timedelta(hours=1),
                last_error="OpenAI web search response was incomplete",
            ),
        ]
    )
    db_session.commit()
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in (
        "sec_items",
        "spglobal_index_items",
        "alpaca_items",
    ):
        monkeypatch.setattr(news_digest, source, lambda *args: [])
    calls = []

    class FakeWebDiscovery:
        def available(self):
            return True

        def search(self, *args):
            calls.append("search")
            raise ValueError("OpenAI web search incomplete: max_output_tokens")

    monkeypatch.setattr(news_digest, "OpenAIWebNewsDiscovery", FakeWebDiscovery)

    news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object())
    state = db_session.get(NewsSyncState, "openai_web:SNDK")
    assert calls == ["search"]
    assert state.next_attempt_at.replace(tzinfo=timezone.utc) == now + timedelta(minutes=30)

    news_digest.run_news_sync(db_session, FailedAnalyser(), now + timedelta(minutes=5), http=object())
    assert calls == ["search"]


def test_manual_sync_overrides_saved_source_and_web_search_timers(db_session, monkeypatch):
    now = datetime(2026, 9, 27, 17, tzinfo=timezone.utc)
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk", exchange="NASDAQ")
    blocked_until = now + timedelta(hours=1)
    db_session.add(entry)
    for key in ("rss:test", "alpaca:SNDK", "openai_web:SNDK"):
        db_session.add(
            NewsSyncState(
                source_key=key,
                last_attempt_at=now - timedelta(minutes=5),
                last_error="previous failure",
                next_attempt_at=blocked_until,
            )
        )
    db_session.commit()
    calls = []
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {"test": "https://example.com/rss"})
    monkeypatch.setattr(news_digest, "rss_items", lambda *args: calls.append("rss") or [])
    monkeypatch.setattr(news_digest, "alpaca_items", lambda *args: calls.append("alpaca") or [])
    for source in ("sec_items", "spglobal_index_items"):
        monkeypatch.setattr(news_digest, source, lambda *args: [])

    class FakeWebDiscovery:
        def available(self):
            return True

        def search(self, *args):
            calls.append("web")
            return []

    monkeypatch.setattr(news_digest, "OpenAIWebNewsDiscovery", FakeWebDiscovery)

    news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object(), force=True)

    assert calls == ["rss", "alpaca", "web"]


def test_refresh_replays_full_seven_days_after_recent_source_success(db_session, monkeypatch):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    now = datetime(2026, 9, 27, 3, 50, tzinfo=timezone.utc)
    db_session.add_all([entry, NewsSyncState(source_key="alpaca", last_success_at=now)])
    db_session.commit()
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in ("sec_items", "spglobal_index_items"):
        monkeypatch.setattr(news_digest, source, lambda *args: [])

    def alpaca_fixture(http, symbols, since, until):
        assert since == now.replace(day=20)
        return [
            SourceItem(
                "alpaca",
                "61915823",
                "https://example.com/rosenblatt-sndk",
                "Rosenblatt Initiates Coverage On SanDisk with Buy Rating, Announces Price Target of $2400",
                "",
                datetime(2026, 9, 22, 11, 43, 45, tzinfo=timezone.utc),
                ("SNDK",),
            )
        ]

    monkeypatch.setattr(news_digest, "alpaca_items", alpaca_fixture)
    result = news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object())

    assert result["alpaca:SNDK"] == 1
    assert db_session.query(NewsStory).one().status == "pending"
    assert db_session.query(NewsStory).one().released_at.date().isoformat() == "2026-09-22"
    run = db_session.query(NewsCollectionRun).one()
    assert (run.new_source_count, run.new_card_count) == (1, 0)


def test_alpaca_failure_for_one_stock_does_not_block_another(db_session, monkeypatch):
    entries = [
        WatchlistEntry(alpaca_asset_id="asset-a", symbol="AAAA", name="Alpha Inc", exchange="NASDAQ"),
        WatchlistEntry(alpaca_asset_id="asset-b", symbol="BBBB", name="Beta Inc", exchange="NASDAQ"),
    ]
    db_session.add_all(entries)
    db_session.commit()
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in ("sec_items", "spglobal_index_items"):
        monkeypatch.setattr(news_digest, source, lambda *args: [])
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)

    def alpaca_fixture(http, symbols, since, until):
        if symbols == ["AAAA"]:
            raise httpx.ConnectError("provider unavailable")
        return [
            SourceItem(
                "alpaca",
                "beta-result",
                "https://example.com/beta",
                "Beta announces quarterly results",
                "",
                now,
                ("BBBB",),
            )
        ]

    monkeypatch.setattr(news_digest, "alpaca_items", alpaca_fixture)
    result = news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object())

    assert "alpaca:AAAA" not in result
    assert result["alpaca:BBBB"] == 1
    assert db_session.get(NewsSyncState, "alpaca:AAAA").last_error
    assert db_session.query(NewsStory).one().headline == "Beta announces quarterly results"


def test_manual_refresh_preserves_provider_access_cooldown(db_session, monkeypatch):
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    entry = WatchlistEntry(alpaca_asset_id="asset-a", symbol="AAAA", name="Alpha Inc", exchange="NASDAQ")
    db_session.add_all(
        [
            entry,
            NewsSyncState(
                source_key="rss:blocked",
                last_error="HTTP 403 Forbidden",
                next_attempt_at=now + timedelta(days=1),
            ),
        ]
    )
    db_session.commit()
    calls = []
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {"blocked": "https://example.com/rss"})
    monkeypatch.setattr(news_digest, "rss_items", lambda *args: calls.append("rss") or [])
    monkeypatch.setattr(news_digest, "alpaca_items", lambda *args: calls.append("alpaca") or [])
    monkeypatch.setattr(news_digest, "sec_items", lambda *args: [])
    monkeypatch.setattr(news_digest, "spglobal_index_items", lambda *args: [])

    news_digest.run_news_sync(db_session, FailedAnalyser(), now, http=object(), force=True)

    assert calls == ["alpaca"]
    run = db_session.query(NewsCollectionRun).one()
    assert run.skipped_sources == ["rss:blocked"]
    assert all(not key.startswith("gdelt:") for key in news_digest.active_news_source_keys([entry]))


def test_twelve_stock_inventory_has_thirty_one_active_jobs(monkeypatch):
    entries = [
        WatchlistEntry(
            alpaca_asset_id=f"asset-{index}",
            symbol=f"T{index}",
            name=f"Test {index}",
            exchange="NASDAQ",
        )
        for index in range(12)
    ]
    monkeypatch.setattr(
        news_digest,
        "configured_feeds",
        lambda: {
            "prnewswire": "https://example.com/pr",
            "globenewswire_public": "https://example.com/gn",
            "ir_amd": "https://example.com/amd",
            "ir_fps": "https://example.com/fps",
            "ir_mrvl": "https://example.com/mrvl",
        },
    )
    monkeypatch.setattr(news_digest.settings, "openai_news_enabled", True)
    monkeypatch.setattr(news_digest.settings, "openai_news_web_search_enabled", True)
    monkeypatch.setattr(news_digest.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(news_digest.settings, "finnhub_api_key", None)

    keys = news_digest.active_news_source_keys(entries)

    assert len(keys) == 31
    assert sum(key.startswith("openai_web:") for key in keys) == 12
    assert sum(key.startswith("alpaca:") for key in keys) == 12
    assert not any(key.startswith("gdelt:") or key == "rss:ir_be" for key in keys)


def test_web_discovery_fetches_independent_stocks_concurrently(db_session, monkeypatch):
    entries = [
        WatchlistEntry(alpaca_asset_id=f"asset-{symbol}", symbol=symbol, name=symbol, exchange="NASDAQ")
        for symbol in ("AAAA", "BBBB")
    ]
    db_session.add_all(entries)
    db_session.commit()
    monkeypatch.setattr(news_digest, "configured_feeds", lambda: {})
    for source in ("alpaca_items", "sec_items", "spglobal_index_items"):
        monkeypatch.setattr(news_digest, source, lambda *args: [])
    barrier = Barrier(2)

    class ConcurrentDiscovery:
        def available(self):
            return True

        def search(self, entry, since, until, http):
            barrier.wait(timeout=2)
            return []

    monkeypatch.setattr(news_digest, "OpenAIWebNewsDiscovery", ConcurrentDiscovery)
    result = news_digest.run_news_sync(
        db_session, FailedAnalyser(), datetime(2026, 9, 27, tzinfo=timezone.utc)
    )

    assert "openai_web:AAAA" in result
    assert "openai_web:BBBB" in result


def test_retry_pending_releases_sqlite_write_lock_before_next_token_reservation():
    name = f"news_retry_{uuid4().hex}"
    engine = create_engine(
        f"sqlite:///file:{name}?mode=memory&cache=shared&uri=true",
        connect_args={"uri": True, "timeout": 0.1},
        poolclass=QueuePool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with session_factory() as db:
            entry = WatchlistEntry(
                alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ"
            )
            db.add(entry)
            db.commit()
            now = datetime(2026, 9, 26, 15, tzinfo=timezone.utc)
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
                for number in range(1, 4)
            ]
            assert ingest_items(db, items, [entry], FailedAnalyser(), now, [0]) == 3

            token_budget = DailyNewsTokenBudget(100_000, session_factory=session_factory)

            class BudgetedAnalyser(FakeAnalyser):
                model = "budgeted-model"
                calls = 0

                def analyse(self, entries, evidence, exposures):
                    self.calls += 1
                    try:
                        day = token_budget.reserve(100)
                    except SQLAlchemyError:
                        return None
                    if day is None:
                        return None
                    token_budget.settle(day, 100, 20)
                    if self.calls == 1:
                        return ModelAnalysis(
                            relevant=False,
                            affectedAssetIds=[],
                            category="deal",
                            direction="unclear",
                            headline="Irrelevant",
                            shortSummary="",
                            detailSummary="",
                            keyFacts=[],
                            unknowns=[],
                            relevanceReason="",
                            supportingSourceIds=[],
                        )
                    return super().analyse(entries, evidence, exposures)

            assert retry_pending(db, [entry], BudgetedAnalyser(), now, [3]) == 3
            assert db.query(NewsStory).filter_by(status="irrelevant").count() == 1
            assert db.query(NewsStory).filter_by(status="ready").count() == 2
            assert db.query(NewsStory).filter_by(status="pending").count() == 0
            assert db.query(NewsAiDailyUsage).one().requests == 3
    finally:
        engine.dispose()
