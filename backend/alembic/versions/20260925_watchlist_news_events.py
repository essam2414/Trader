"""Store watchlist catalyst stories, source observations, and scheduled events.

Revision ID: 20260925_news_events
Revises: 20260923_incremental_history
"""

import sqlalchemy as sa

from alembic import op

revision = "20260925_news_events"
down_revision = "20260923_incremental_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("news_source_items"):
        op.create_table(
            "news_source_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("source_key", sa.String(512), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("excerpt", sa.Text(), nullable=False),
            sa.Column("candidate_symbols", sa.JSON(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.UniqueConstraint("provider", "source_key", name="uq_news_source_item"),
        )
    if not inspector.has_table("news_stories"):
        op.create_table(
            "news_stories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("headline", sa.Text(), nullable=False),
            sa.Column("short_summary", sa.Text(), nullable=False),
            sa.Column("detail_summary", sa.Text(), nullable=False),
            sa.Column("relevance_reason", sa.Text(), nullable=False),
            sa.Column("key_facts", sa.JSON(), nullable=False),
            sa.Column("unknowns", sa.JSON(), nullable=False),
            sa.Column("category", sa.String(32), nullable=False),
            sa.Column("direction", sa.String(16), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("released_at", sa.DateTime(timezone=True)),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("model_version", sa.String(100)),
        )
    if not inspector.has_table("news_story_sources"):
        op.create_table(
            "news_story_sources",
            sa.Column("story_id", sa.Integer(), sa.ForeignKey("news_stories.id"), primary_key=True),
            sa.Column(
                "source_item_id", sa.Integer(), sa.ForeignKey("news_source_items.id"), primary_key=True
            ),
        )
    if not inspector.has_table("news_story_stocks"):
        op.create_table(
            "news_story_stocks",
            sa.Column("story_id", sa.Integer(), sa.ForeignKey("news_stories.id"), primary_key=True),
            sa.Column("alpaca_asset_id", sa.String(36), primary_key=True),
        )
    if not inspector.has_table("market_events"):
        op.create_table(
            "market_events",
            sa.Column("event_key", sa.String(256), primary_key=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("category", sa.String(40), nullable=False),
            sa.Column("scope", sa.String(20), nullable=False),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("previous_event_date", sa.Date()),
            sa.Column("starts_at", sa.DateTime(timezone=True)),
            sa.Column("time_precision", sa.String(16), nullable=False),
            sa.Column("date_status", sa.String(16), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_market_events_event_date", "market_events", ["event_date"])
    if not inspector.has_table("market_event_stocks"):
        op.create_table(
            "market_event_stocks",
            sa.Column(
                "event_key", sa.String(256), sa.ForeignKey("market_events.event_key"), primary_key=True
            ),
            sa.Column("alpaca_asset_id", sa.String(36), primary_key=True),
        )
    if not inspector.has_table("news_sync_states"):
        op.create_table(
            "news_sync_states",
            sa.Column("source_key", sa.String(128), primary_key=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
            sa.Column("last_success_at", sa.DateTime(timezone=True)),
            sa.Column("last_error", sa.String(500)),
        )


def downgrade() -> None:
    for table in (
        "news_sync_states",
        "market_event_stocks",
        "market_events",
        "news_story_stocks",
        "news_story_sources",
        "news_stories",
        "news_source_items",
    ):
        op.drop_table(table)
