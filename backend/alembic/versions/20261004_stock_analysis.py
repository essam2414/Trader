"""Persist latest stock analysis without changing portfolio or news data."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_stock_analysis"
down_revision = "20261004_news_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("stock_analysis_snapshots"):
        op.create_table(
            "stock_analysis_snapshots",
            sa.Column("alpaca_asset_id", sa.String(36), primary_key=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("stock_analysis_snapshots")
