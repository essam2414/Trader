"""Convert stored ambiguous news direction to unclear.

Revision ID: 20260926_news_direction
Revises: 20260925_news_ai_budget
"""

import sqlalchemy as sa

from alembic import op

revision = "20260926_news_direction"
down_revision = "20260925_news_ai_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE news_stories SET direction = 'unclear' WHERE direction = 'mixed'"))


def downgrade() -> None:
    # The original direction cannot be recovered from an unclear value.
    pass
