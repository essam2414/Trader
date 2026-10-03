"""Retain historical FX rates so history sync can resume within its time budget.

Revision ID: 20261003_historical_fx_rates
Revises: 20261003_trends_preferences
"""

import sqlalchemy as sa

from alembic import op

revision = "20261003_historical_fx_rates"
down_revision = "20261003_trends_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # App startup can create new ORM tables before Alembic is run.
    if sa.inspect(op.get_bind()).has_table("historical_fx_rates"):
        return
    op.create_table(
        "historical_fx_rates",
        sa.Column("rate_date", sa.Date(), primary_key=True),
        sa.Column("from_currency", sa.String(3), primary_key=True),
        sa.Column("to_currency", sa.String(3), primary_key=True),
        sa.Column("rate", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("historical_fx_rates")
