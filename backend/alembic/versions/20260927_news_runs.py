"""Record outcomes for each news collection run.

Revision ID: 20260927_news_runs
Revises: 20260927_news_reliability
"""

import sqlalchemy as sa

from alembic import op

revision = "20260927_news_runs"
down_revision = "20260927_news_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_collection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("failed_sources", sa.JSON(), nullable=False),
        sa.Column("skipped_sources", sa.JSON(), nullable=False),
    )
    op.create_index("ix_news_collection_runs_started_at", "news_collection_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_news_collection_runs_started_at", table_name="news_collection_runs")
    op.drop_table("news_collection_runs")
