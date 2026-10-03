"""Historical cards can be consolidated without deleting provenance."""

from datetime import date, datetime, timezone

from app.models import (
    MarketEvent,
    MarketEventStock,
    NewsSourceItem,
    NewsStory,
    NewsStorySource,
    NewsStoryStock,
    WatchlistEntry,
)
from app.services.news_reconcile import apply_analyst_merges, plan_analyst_merges, plan_event_merges


def test_reconcile_sandisk_initiation_keeps_sources_and_original_date(db_session):
    stock = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    db_session.add(stock)
    released = datetime(2026, 9, 22, 9, 15, tzinfo=timezone.utc)
    found = datetime(2026, 9, 27, 14, 27, tzinfo=timezone.utc)
    records = [
        ("Rosenblatt Initiates Sandisk at Buy With $2,400 Price Target", "", released),
        (
            "This SanDisk Analyst Begins Coverage On A Bullish Note",
            "Rosenblatt analyst Kevin Cassidy initiated coverage on SanDisk Corp (NASDAQ: SNDK) "
            "with a Buy rating and announced a price target of $2,400.",
            released,
        ),
        (
            "SanDisk Stock Price Forecast — Rosenblatt Analyst Sees 36% Upside",
            "Rosenblatt initiated SanDisk at Buy with a $2,400 price target.",
            None,
        ),
    ]
    for index, (title, excerpt, published) in enumerate(records):
        story = NewsStory(
            headline="Rosenblatt initiates Sandisk at Buy with $2,400 target",
            status="ready",
            category="analyst" if index < 2 else "guidance",
            direction="upside",
            released_at=published,
            first_seen_at=found,
            updated_at=found,
        )
        source = NewsSourceItem(
            provider="test",
            source_key=str(index),
            url=f"https://example.com/{index}",
            title=title,
            excerpt=excerpt,
            candidate_symbols=["SNDK"],
            published_at=published,
            first_seen_at=found,
            content_hash=str(index),
        )
        db_session.add_all([story, source])
        db_session.flush()
        db_session.add_all(
            [
                NewsStorySource(story_id=story.id, source_item_id=source.id),
                NewsStoryStock(story_id=story.id, alpaca_asset_id=stock.alpaca_asset_id),
            ]
        )
    db_session.commit()

    plans = plan_analyst_merges(db_session)
    assert len(plans) == 1
    assert len(plans[0].duplicate_ids) == 2
    assert plans[0].released_at == released

    assert apply_analyst_merges(db_session, plans, found) == 2
    survivor = db_session.get(NewsStory, plans[0].survivor_id)
    assert survivor.status == "ready"
    assert survivor.released_at.replace(tzinfo=timezone.utc) == released
    assert db_session.query(NewsStorySource).filter_by(story_id=survivor.id).count() == 3
    assert db_session.query(NewsStory).filter_by(status="merged").count() == 2
    assert plan_analyst_merges(db_session) == []


def test_roundup_articles_about_one_upcoming_earnings_report_form_one_card(db_session):
    stock = WatchlistEntry(
        alpaca_asset_id="asset-mu", symbol="MU", name="Micron Technology", exchange="NASDAQ"
    )
    event = MarketEvent(
        event_key="earnings:mu:2026-q4",
        title="Micron fiscal Q4 earnings",
        category="earnings",
        scope="watchlist",
        event_date=date(2026, 9, 30),
        time_precision="date_only",
        date_status="estimated",
        source_url="https://example.com/calendar",
        last_verified_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    db_session.add_all([stock, event])
    db_session.flush()
    db_session.add(MarketEventStock(event_key=event.event_key, alpaca_asset_id=stock.alpaca_asset_id))
    headlines = [
        "Micron to report fourth-quarter earnings this week",
        "Micron heads into Sept. 30 earnings with AI-memory demand in focus",
        "Micron set for fiscal Q4 earnings with guidance in focus",
    ]
    for index, headline in enumerate(headlines):
        seen = datetime(2026, 9, 25 + index, tzinfo=timezone.utc)
        story = NewsStory(
            headline=headline,
            status="ready",
            category="earnings",
            direction="unclear",
            released_at=seen,
            first_seen_at=seen,
            updated_at=seen,
        )
        source = NewsSourceItem(
            provider="alpaca",
            source_key=str(index),
            url=f"https://example.com/{index}",
            title=f"Different broad market roundup {index}",
            excerpt=headline,
            candidate_symbols=["MU"],
            published_at=seen,
            first_seen_at=seen,
            content_hash=str(index),
        )
        db_session.add_all([story, source])
        db_session.flush()
        db_session.add_all(
            [
                NewsStorySource(story_id=story.id, source_item_id=source.id),
                NewsStoryStock(story_id=story.id, alpaca_asset_id=stock.alpaca_asset_id),
            ]
        )
    db_session.commit()

    plans = plan_event_merges(db_session)
    assert len(plans) == 1
    assert len(plans[0].duplicate_ids) == 2
    assert apply_analyst_merges(db_session, plans, datetime(2026, 9, 27, tzinfo=timezone.utc)) == 2
    assert db_session.query(NewsStory).filter_by(status="ready").count() == 1
    assert db_session.query(NewsStorySource).filter_by(story_id=plans[0].survivor_id).count() == 3


def test_micron_previews_across_other_and_analyst_categories_share_one_event(db_session):
    stock = WatchlistEntry(
        alpaca_asset_id="asset-mu", symbol="MU", name="Micron Technology", exchange="NASDAQ"
    )
    event = MarketEvent(
        event_key="earnings:mu:2026-q4",
        title="Micron fiscal Q4 earnings",
        category="earnings",
        scope="watchlist",
        event_date=date(2026, 9, 30),
        time_precision="date_only",
        date_status="estimated",
        source_url="https://example.com/calendar",
        last_verified_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    db_session.add_all([stock, event])
    db_session.flush()
    db_session.add(MarketEventStock(event_key=event.event_key, alpaca_asset_id=stock.alpaca_asset_id))
    cases = [
        (
            "earnings",
            "Micron expected to report strong fourth-quarter results soon",
            "Micron is due to release results next week.",
        ),
        (
            "other",
            "Micron could face a stronger-than-guided Q4 revenue print on Sept. 30",
            "Micron may report revenue above estimates when it reports results.",
        ),
        (
            "other",
            "Micron's upcoming fiscal Q4 results may highlight AI/HBM demand",
            "Its Sept. 30 results could be an important catalyst.",
        ),
        (
            "analyst",
            "Micron eyes higher Q4 earnings as analysts reaffirm bullish targets",
            "Analysts reiterated ratings ahead of its fiscal Q4 earnings release.",
        ),
    ]
    for index, (category, headline, summary) in enumerate(cases):
        seen = datetime(2026, 9, 20 + index, tzinfo=timezone.utc)
        story = NewsStory(
            headline=headline,
            short_summary=summary,
            status="ready",
            category=category,
            direction="unclear",
            released_at=seen,
            first_seen_at=seen,
            updated_at=seen,
        )
        db_session.add(story)
        db_session.flush()
        db_session.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=stock.alpaca_asset_id))
    db_session.commit()

    plans = plan_event_merges(db_session)
    assert len(plans) == 1
    assert len(plans[0].duplicate_ids) == 3


def test_analyst_roundup_merges_by_card_event_not_roundup_title(db_session):
    stock = WatchlistEntry(
        alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk Corporation", exchange="NASDAQ"
    )
    db_session.add(stock)
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    for index, (headline, title) in enumerate(
        [
            ("Rosenblatt initiates Sandisk at Buy with $2,400 target", "Rosenblatt covers Sandisk"),
            (
                "Rosenblatt initiates Sandisk with Buy, $2400 target",
                "On Holding, Viking Therapeutics, Shopify And Other Big Stocks Moving Higher",
            ),
        ]
    ):
        story = NewsStory(
            headline=headline,
            status="ready",
            category="analyst",
            direction="upside",
            released_at=now,
            first_seen_at=now,
            updated_at=now,
        )
        source = NewsSourceItem(
            provider="alpaca",
            source_key=str(index),
            url=f"https://example.com/{index}",
            title=title,
            excerpt="Sandisk: Rosenblatt initiated Buy with a $2400 target.",
            candidate_symbols=["SNDK"],
            published_at=now,
            first_seen_at=now,
            content_hash=str(index),
        )
        db_session.add_all([story, source])
        db_session.flush()
        db_session.add_all(
            [
                NewsStorySource(story_id=story.id, source_item_id=source.id),
                NewsStoryStock(story_id=story.id, alpaca_asset_id=stock.alpaca_asset_id),
            ]
        )
    db_session.commit()

    plans = plan_event_merges(db_session)
    assert len(plans) == 1
    assert len(plans[0].duplicate_ids) == 1


def test_target_raise_uses_new_target_when_old_target_is_also_quoted(db_session):
    stock = WatchlistEntry(alpaca_asset_id="asset-now", symbol="NOW", name="ServiceNow", exchange="NYSE")
    db_session.add(stock)
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    for headline in (
        "Cantor Fitzgerald raises ServiceNow target to $174 and keeps Overweight",
        "Cantor Fitzgerald raises ServiceNow price target to $174 from $141 and keeps Overweight",
    ):
        story = NewsStory(
            headline=headline,
            status="ready",
            category="analyst",
            direction="upside",
            released_at=now,
            first_seen_at=now,
            updated_at=now,
        )
        db_session.add(story)
        db_session.flush()
        db_session.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=stock.alpaca_asset_id))
    db_session.commit()

    plans = plan_event_merges(db_session)
    assert len(plans) == 1
    assert len(plans[0].duplicate_ids) == 1


def test_acquisition_announcement_and_industry_paraphrases_merge_conservatively(db_session):
    stocks = [
        WatchlistEntry(alpaca_asset_id="asset-vrt", symbol="VRT", name="Vertiv", exchange="NYSE"),
        WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk", exchange="NASDAQ"),
    ]
    db_session.add_all(stocks)
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    cases = [
        (stocks[0], "deal", "Vertiv agrees to acquire King Environmental Services to expand cooling"),
        (stocks[0], "deal", "Vertiv announces agreement to acquire King Environmental Services"),
        (stocks[0], "deal", "Vertiv to acquire King Environmental Services"),
        (stocks[0], "deal", "Vertiv completes acquisition of King Environmental Services"),
        (
            stocks[1],
            "industry",
            "Sandisk says AI inference is reshaping NAND demand; "
            "signed strategic agreements support storage outlook",
        ),
        (
            stocks[1],
            "industry",
            "Sandisk says AI inference is expanding NAND demand and signed eight strategic supply agreements",
        ),
    ]
    for stock, category, headline in cases:
        story = NewsStory(
            headline=headline,
            status="ready",
            category=category,
            direction="unclear",
            released_at=now,
            first_seen_at=now,
            updated_at=now,
        )
        db_session.add(story)
        db_session.flush()
        db_session.add(NewsStoryStock(story_id=story.id, alpaca_asset_id=stock.alpaca_asset_id))
    db_session.commit()

    plans = plan_event_merges(db_session)

    assert len(plans) == 2
    assert sorted(len(plan.duplicate_ids) for plan in plans) == [1, 2]
