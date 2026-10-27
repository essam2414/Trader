"""Record useful output separately from completed source jobs.

Revision ID: 20260927_news_run_output
Revises: 20260927_restore_ready_news
"""

import sqlalchemy as sa

from alembic import op

revision = "20260927_news_run_output"
down_revision = "20260927_restore_ready_news"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_collection_runs",
        sa.Column("new_source_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "news_collection_runs",
        sa.Column("new_card_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("news_collection_runs", "new_card_count")
    op.drop_column("news_collection_runs", "new_source_count")
