"""Persist development identities and publication decisions independently of article titles."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_news_identity"
down_revision = "20261003_historical_fx_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("news_stories")}
    for column in (
        sa.Column("event_descriptor", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("identity_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_dirty", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("related_story_id", sa.Integer(), nullable=True),
    ):
        if column.name not in columns:
            op.add_column("news_stories", column)
    if not sa.inspect(op.get_bind()).has_table("news_event_identities"):
        op.create_table(
            "news_event_identities",
            sa.Column("event_key", sa.String(256), primary_key=True),
            sa.Column("story_id", sa.Integer(), sa.ForeignKey("news_stories.id"), nullable=False),
        )
        op.create_index("ix_news_event_identities_story_id", "news_event_identities", ["story_id"])
    if not sa.inspect(op.get_bind()).has_table("news_resolution_decisions"):
        op.create_table(
            "news_resolution_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("story_id", sa.Integer(), sa.ForeignKey("news_stories.id"), nullable=False),
            sa.Column("matched_story_id", sa.Integer(), nullable=True),
            sa.Column("outcome", sa.String(32), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("evidence_hash", sa.String(64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_news_resolution_decisions_story_id", "news_resolution_decisions", ["story_id"])


def downgrade() -> None:
    op.drop_table("news_resolution_decisions")
    op.drop_table("news_event_identities")
    for name in ("related_story_id", "summary_dirty", "identity_version", "event_descriptor"):
        op.drop_column("news_stories", name)
