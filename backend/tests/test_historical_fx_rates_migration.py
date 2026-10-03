"""Historical FX cache upgrades preserve data created by application startup."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, insert, select

from app.models import HistoricalFxRate


@pytest.mark.parametrize("created_by_startup", [False, True])
def test_migration_creates_or_preserves_historical_rates(monkeypatch, created_by_startup):
    path = Path(__file__).parents[1] / "alembic/versions/20261003_historical_fx_rates.py"
    spec = importlib.util.spec_from_file_location("historical_fx_rates_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    table = HistoricalFxRate.__table__
    with engine.begin() as connection:
        if created_by_startup:
            table.create(connection)
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        connection.execute(
            insert(table),
            {"rate_date": date(2026, 10, 2), "from_currency": "USD", "to_currency": "GBP", "rate": 0.8},
        )
        migration.upgrade()
        assert connection.execute(select(table.c.rate)).scalar_one() == 0.8
