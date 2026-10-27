"""The Trends migration tolerates tables created by application startup."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.models import TrendsPreferences


@pytest.mark.parametrize("created_by_startup", [False, True])
def test_migration_creates_or_preserves_layout_table(monkeypatch, created_by_startup):
    path = Path(__file__).parents[1] / "alembic/versions/20261003_trends_preferences.py"
    spec = importlib.util.spec_from_file_location("trends_preferences_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        if created_by_startup:
            TrendsPreferences.__table__.create(connection)
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        connection.execute(
            text("INSERT INTO trends_preferences (id, asset_ids, chart_range) VALUES (1, '[]', '3M')")
        )
        migration.upgrade()
        assert connection.execute(text("SELECT chart_range FROM trends_preferences")).scalar() == "3M"
        assert {column["name"] for column in inspect(connection).get_columns("trends_preferences")} == {
            "id",
            "asset_ids",
            "chart_range",
        }
