"""Track conservative daily OpenAI news token use.

Revision ID: 20260925_news_ai_budget
Revises: 20260925_news_events
"""

import sqlalchemy as sa

from alembic import op

revision = "20260925_news_ai_budget"
down_revision = "20260925_news_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("news_ai_daily_usage"):
        op.create_table(
            "news_ai_daily_usage",
            sa.Column("day", sa.Date(), primary_key=True),
            sa.Column("reserved_tokens", sa.Integer(), nullable=False),
            sa.Column("used_tokens", sa.Integer(), nullable=False),
            sa.Column("requests", sa.Integer(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("news_ai_daily_usage")
