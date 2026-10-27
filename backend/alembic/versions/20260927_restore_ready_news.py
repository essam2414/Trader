"""Restore completed summaries that an unsuccessful reanalysis marked pending.

Revision ID: 20260927_restore_ready_news
Revises: 20260927_news_runs
"""

import sqlalchemy as sa

from alembic import op

revision = "20260927_restore_ready_news"
down_revision = "20260927_news_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE news_stories SET status = 'ready' "
            "WHERE status = 'pending' AND model_version IS NOT NULL "
            "AND detail_summary <> '' AND short_summary <> ''"
        )
    )


def downgrade() -> None:
    # A recovered summary remains a valid completed summary.
    pass
