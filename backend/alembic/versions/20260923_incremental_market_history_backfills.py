"""add resumable cursors for every market-history backfill

Revision ID: 20260923_incremental_history
Revises: 20260923_market_history
Create Date: 2026-09-23
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_incremental_history"
down_revision = "20260923_market_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("market_history_sync_states")}
    if "daily_backfill_cursor" not in columns:
        op.add_column(
            "market_history_sync_states",
            sa.Column("daily_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
        )
    if "corporate_actions_backfill_cursor" not in columns:
        op.add_column(
            "market_history_sync_states",
            sa.Column("corporate_actions_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("market_history_sync_states") as batch_op:
        batch_op.drop_column("corporate_actions_backfill_cursor")
        batch_op.drop_column("daily_backfill_cursor")
