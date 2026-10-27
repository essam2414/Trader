"""New revision upgrades an existing local database schema."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app import models  # noqa: F401
from app.db import Base


def test_news_revision_creates_expected_tables_on_existing_schema():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    new_tables = [
        "news_sync_states",
        "market_event_stocks",
        "market_events",
        "news_story_stocks",
        "news_story_sources",
        "news_stories",
        "news_source_items",
    ]
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20260925_watchlist_news_events.py"
    spec = importlib.util.spec_from_file_location("watchlist_news_revision", path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    with engine.begin() as connection:
        for name in new_tables:
            Base.metadata.tables[name].drop(connection)
        revision.op = Operations(MigrationContext.configure(connection))
        revision.upgrade()
        inspector = sa.inspect(connection)
        assert set(new_tables) <= set(inspector.get_table_names())
        assert "previous_event_date" in {column["name"] for column in inspector.get_columns("market_events")}
        assert "candidate_symbols" in {
            column["name"] for column in inspector.get_columns("news_source_items")
        }


def test_direction_revision_converts_existing_mixed_stories_to_unclear():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20260926_news_direction.py"
    spec = importlib.util.spec_from_file_location("news_direction_revision", path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO news_stories (id, headline, short_summary, detail_summary, "
                "relevance_reason, key_facts, unknowns, category, direction, status, "
                "first_seen_at, updated_at) VALUES (1, 'Test', '', '', '', '[]', '[]', "
                "'other', 'mixed', 'ready', '2026-09-26', '2026-09-26')"
            )
        )
        revision.op = Operations(MigrationContext.configure(connection))
        revision.upgrade()
        assert connection.scalar(sa.text("SELECT direction FROM news_stories WHERE id = 1")) == "unclear"


def test_identity_migration_preserves_existing_cards_and_is_safe_after_create_all():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    path = Path(__file__).parents[1] / "alembic/versions/20261004_news_identity.py"
    spec = importlib.util.spec_from_file_location("news_identity_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with engine.begin() as connection:
        revision.op = Operations(MigrationContext.configure(connection))
        revision.downgrade()
        connection.execute(
            sa.text(
                "INSERT INTO news_stories (id, headline, short_summary, detail_summary, relevance_reason, "
                "key_facts, unknowns, category, direction, status, first_seen_at, updated_at) "
                "VALUES (1, 'Saved story', '', '', '', '[]', '[]', 'earnings', 'unclear', 'ready', "
                "'2026-10-03', '2026-10-03')"
            )
        )
        revision.upgrade()
        revision.upgrade()
        row = connection.execute(
            sa.text("SELECT headline, status, identity_version, summary_dirty FROM news_stories WHERE id=1")
        ).one()
        assert tuple(row) == ("Saved story", "ready", 0, 0)
        assert {"news_event_identities", "news_resolution_decisions"} <= set(
            sa.inspect(connection).get_table_names()
        )


def test_analysis_migration_preserves_retry_state_and_round_trips():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    path = Path(__file__).parents[1] / "alembic/versions/20261006_news_analysis_reliability.py"
    spec = importlib.util.spec_from_file_location("news_analysis_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with engine.begin() as connection:
        revision.op = Operations(MigrationContext.configure(connection))
        revision.downgrade()
        connection.execute(
            sa.text(
                "INSERT INTO news_sync_states (source_key, last_error) "
                "VALUES ('analysis:42', 'Rejected number')"
            )
        )
        revision.upgrade()
        revision.upgrade()
        row = connection.execute(
            sa.text(
                "SELECT last_error, failure_count, failure_kind FROM news_sync_states "
                "WHERE source_key='analysis:42'"
            )
        ).one()
        assert tuple(row) == ("Rejected number", 0, None)
        assert sa.inspect(connection).has_table("news_comparison_cache")
        revision.downgrade()
        assert connection.scalar(sa.text("SELECT last_error FROM news_sync_states")) == "Rejected number"
