"""add canonical market history tables

Revision ID: 20260923_market_history
Revises: 20260921_native_cursor
Create Date: 2026-09-23
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_market_history"
down_revision = "20260921_native_cursor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("market_price_bars"):
        op.create_table(
            "market_price_bars",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("alpaca_asset_id", sa.String(length=36), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("interval_seconds", sa.Integer(), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("open", sa.Numeric(20, 8), nullable=False),
            sa.Column("high", sa.Numeric(20, 8), nullable=False),
            sa.Column("low", sa.Numeric(20, 8), nullable=False),
            sa.Column("close", sa.Numeric(20, 8), nullable=False),
            sa.Column("volume", sa.BigInteger(), nullable=False),
            sa.Column("trade_count", sa.Integer(), nullable=True),
            sa.Column("vwap", sa.Numeric(20, 8), nullable=True),
            sa.Column("session", sa.String(length=16), nullable=False),
            sa.Column("source_feed", sa.String(length=16), nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "alpaca_asset_id", "interval_seconds", "starts_at", name="uq_market_price_bar"
            ),
        )
    _create_index_if_missing(
        inspector, "market_price_bars", "ix_market_price_bars_alpaca_asset_id", ["alpaca_asset_id"]
    )
    _create_index_if_missing(inspector, "market_price_bars", "ix_market_price_bars_starts_at", ["starts_at"])

    if not inspector.has_table("market_corporate_actions"):
        op.create_table(
            "market_corporate_actions",
            sa.Column("provider_id", sa.String(length=64), primary_key=True),
            sa.Column("alpaca_asset_id", sa.String(length=36), nullable=True),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("action_type", sa.String(length=48), nullable=False),
            sa.Column("effective_date", sa.String(length=16), nullable=True),
            sa.Column("raw_data", sa.JSON(), nullable=False),
            sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing(
        inspector,
        "market_corporate_actions",
        "ix_market_corporate_actions_alpaca_asset_id",
        ["alpaca_asset_id"],
    )
    _create_index_if_missing(
        inspector, "market_corporate_actions", "ix_market_corporate_actions_symbol", ["symbol"]
    )

    if not inspector.has_table("market_history_sync_states"):
        op.create_table(
            "market_history_sync_states",
            sa.Column("alpaca_asset_id", sa.String(length=36), primary_key=True),
            sa.Column("five_minute_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
            sa.Column("five_minute_backfilled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("one_minute_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
            sa.Column("one_minute_backfilled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("daily_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
            sa.Column("daily_backfilled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_sip_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("corporate_actions_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
            sa.Column("corporate_actions_synced_at", sa.DateTime(timezone=True), nullable=True),
        )
    else:
        _add_column_if_missing(
            inspector,
            "market_history_sync_states",
            sa.Column("five_minute_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "market_history_sync_states",
            sa.Column("one_minute_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "market_history_sync_states",
            sa.Column("one_minute_backfilled_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "market_history_sync_states",
            sa.Column("daily_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "market_history_sync_states",
            sa.Column("corporate_actions_synced_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "market_history_sync_states",
            sa.Column("corporate_actions_backfill_cursor", sa.DateTime(timezone=True), nullable=True),
        )


def _create_index_if_missing(
    inspector: sa.Inspector, table_name: str, index_name: str, columns: list[str]
) -> None:
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns)


def _add_column_if_missing(inspector: sa.Inspector, table_name: str, column: sa.Column) -> None:
    existing_columns = {existing["name"] for existing in inspector.get_columns(table_name)}
    if column.name not in existing_columns:
        op.add_column(table_name, column)


def downgrade() -> None:
    op.drop_table("market_history_sync_states")
    op.drop_index("ix_market_corporate_actions_symbol", table_name="market_corporate_actions")
    op.drop_index("ix_market_corporate_actions_alpaca_asset_id", table_name="market_corporate_actions")
    op.drop_table("market_corporate_actions")
    op.drop_index("ix_market_price_bars_starts_at", table_name="market_price_bars")
    op.drop_index("ix_market_price_bars_alpaca_asset_id", table_name="market_price_bars")
    op.drop_table("market_price_bars")
