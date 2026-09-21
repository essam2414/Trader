"""persist native-price backfill progress

Revision ID: 20260921_native_cursor
Revises: 20260921_source_prices
Create Date: 2026-09-21
"""

import sqlalchemy as sa

from alembic import op

revision = "20260921_native_cursor"
down_revision = "20260921_source_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "history_sync_states", sa.Column("continuation_cursor", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("history_sync_states", "continuation_cursor")
