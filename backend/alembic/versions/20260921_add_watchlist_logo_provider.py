"""track the source used for cached watchlist logos

Revision ID: 20260921_logo_provider
Revises: 20260921_watchlist_logos
Create Date: 2026-09-21
"""

import sqlalchemy as sa

from alembic import op

revision = "20260921_logo_provider"
down_revision = "20260921_watchlist_logos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_entries", sa.Column("logo_provider", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlist_entries", "logo_provider")
