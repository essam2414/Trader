"""Keep publication dates with date-only precision honest.

Revision ID: 20260928_news_date_precision
Revises: 20260927_news_run_output
"""

import sqlalchemy as sa

from alembic import op

revision = "20260928_news_date_precision"
down_revision = "20260927_news_run_output"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_source_items",
        sa.Column("published_date_precision", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "news_stories",
        sa.Column("released_date_precision", sa.String(length=16), nullable=True),
    )
    op.add_column("news_source_items", sa.Column("event_date", sa.Date(), nullable=True))
    op.add_column("news_stories", sa.Column("event_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE news_source_items SET published_date_precision = 'minute' WHERE published_at IS NOT NULL"
    )
    op.execute("UPDATE news_stories SET released_date_precision = 'minute' WHERE released_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("news_stories", "event_date")
    op.drop_column("news_source_items", "event_date")
    op.drop_column("news_stories", "released_date_precision")
    op.drop_column("news_source_items", "published_date_precision")
