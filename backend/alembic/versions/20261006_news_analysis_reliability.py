"""Persist bounded analysis retries and completed coverage comparisons."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_news_analysis"
down_revision = "20261004_stock_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("news_sync_states")}
    for column in (
        sa.Column("failure_kind", sa.String(24), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis_input_hash", sa.String(64), nullable=True),
    ):
        if column.name not in columns:
            op.add_column("news_sync_states", column)
    if not sa.inspect(op.get_bind()).has_table("news_comparison_cache"):
        op.create_table(
            "news_comparison_cache",
            sa.Column("input_hash", sa.String(64), primary_key=True),
            sa.Column("decision", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("news_comparison_cache")
    for name in ("analysis_input_hash", "failure_count", "failure_kind"):
        op.drop_column("news_sync_states", name)
