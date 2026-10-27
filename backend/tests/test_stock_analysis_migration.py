"""The snapshot migration is safe before or after startup create_all."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.db import Base


def test_analysis_snapshot_migration_is_idempotent_and_preserves_existing_rows():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    path = Path(__file__).parents[1] / "alembic/versions/20261004_stock_analysis.py"
    spec = importlib.util.spec_from_file_location("stock_analysis_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with engine.begin() as connection:
        revision.op = Operations(MigrationContext.configure(connection))
        revision.downgrade()
        revision.upgrade()
        connection.execute(
            sa.text(
                "INSERT INTO stock_analysis_snapshots (alpaca_asset_id, payload, next_refresh_at) "
                "VALUES ('asset-test', '{}', '2026-10-05T13:00:00')"
            )
        )
        revision.upgrade()
        assert connection.scalar(sa.text("SELECT count(*) FROM stock_analysis_snapshots")) == 1
        assert "order_fills" in sa.inspect(connection).get_table_names()
