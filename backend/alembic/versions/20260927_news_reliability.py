"""Track news publication verification and source cooldowns.

Revision ID: 20260927_news_reliability
Revises: 20260926_news_direction
"""

import sqlalchemy as sa

from alembic import op

revision = "20260927_news_reliability"
down_revision = "20260926_news_direction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_source_items",
        sa.Column("date_status", sa.String(48), nullable=False, server_default="unverified"),
    )
    op.execute("UPDATE news_source_items SET date_status = 'verified' WHERE published_at IS NOT NULL")
    op.add_column("news_sync_states", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("news_sync_states", sa.Column("last_outcome", sa.String(24)))
    op.add_column("news_stories", sa.Column("merged_into_story_id", sa.Integer()))


def downgrade() -> None:
    op.drop_column("news_stories", "merged_into_story_id")
    op.drop_column("news_sync_states", "last_outcome")
    op.drop_column("news_sync_states", "next_attempt_at")
    op.drop_column("news_source_items", "date_status")
