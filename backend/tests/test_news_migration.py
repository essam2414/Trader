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
