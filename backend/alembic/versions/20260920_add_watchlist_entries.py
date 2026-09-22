"""add watchlist entries

Revision ID: 20260920_watchlist
Revises:
Create Date: 2026-09-20
"""

import sqlalchemy as sa

from alembic import op

revision = "20260920_watchlist"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alpaca_asset_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("alpaca_asset_id", name="uq_watchlist_entries_alpaca_asset_id"),
    )


def downgrade() -> None:
    op.drop_table("watchlist_entries")
