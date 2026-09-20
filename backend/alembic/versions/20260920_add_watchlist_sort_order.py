"""add watchlist sort order

Revision ID: 20260920_watchlist_order
Revises: 20260920_watchlist
Create Date: 2026-09-20
"""

import sqlalchemy as sa

from alembic import op

revision = "20260920_watchlist_order"
down_revision = "20260920_watchlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "watchlist_entries",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        "UPDATE watchlist_entries SET sort_order = ranked.sort_order "
        "FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY added_at, id) - 1 AS sort_order "
        "FROM watchlist_entries) AS ranked WHERE watchlist_entries.id = ranked.id"
    )
    with op.batch_alter_table("watchlist_entries") as batch_op:
        batch_op.alter_column("sort_order", server_default=None)


def downgrade() -> None:
    op.drop_column("watchlist_entries", "sort_order")
