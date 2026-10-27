"""Persist the shared Trends stock selection and order.

Revision ID: 20261003_trends_preferences
Revises: 20260928_news_date_precision
"""

import sqlalchemy as sa

from alembic import op

revision = "20261003_trends_preferences"
down_revision = "20260928_news_date_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # App startup can create new ORM tables before Alembic is run.
    if sa.inspect(op.get_bind()).has_table("trends_preferences"):
        return
    op.create_table(
        "trends_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_ids", sa.JSON(), nullable=False),
        sa.Column("chart_range", sa.String(3), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("trends_preferences")
