"""track completion of the history backfill

Revision ID: 20260921_history_sync_state
Revises: 20260921_logo_provider
Create Date: 2026-09-21
"""

import sqlalchemy as sa

from alembic import op

revision = "20260921_history_sync_state"
down_revision = "20260921_logo_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "history_sync_states",
        sa.Column("source", sa.String(length=16), primary_key=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("history_sync_states")
