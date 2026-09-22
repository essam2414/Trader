"""retain native order-fill prices for trade-history display

Revision ID: 20260921_source_prices
Revises: 20260921_history_sync_state
Create Date: 2026-09-21
"""

import sqlalchemy as sa

from alembic import op

revision = "20260921_source_prices"
down_revision = "20260921_history_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_fills", sa.Column("source_price", sa.Float(), nullable=True))
    op.add_column("order_fills", sa.Column("source_currency", sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column("order_fills", "source_currency")
    op.drop_column("order_fills", "source_price")
