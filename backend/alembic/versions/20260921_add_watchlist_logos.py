"""cache watchlist company logos

Revision ID: 20260921_watchlist_logos
Revises: 20260920_watchlist_order
Create Date: 2026-09-21
"""

import sqlalchemy as sa

from alembic import op

revision = "20260921_watchlist_logos"
down_revision = "20260920_watchlist_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_entries", sa.Column("logo_data", sa.LargeBinary(), nullable=True))
    op.add_column("watchlist_entries", sa.Column("logo_content_type", sa.String(length=100), nullable=True))
    op.add_column(
        "watchlist_entries", sa.Column("logo_checked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("watchlist_entries", "logo_checked_at")
    op.drop_column("watchlist_entries", "logo_content_type")
    op.drop_column("watchlist_entries", "logo_data")
