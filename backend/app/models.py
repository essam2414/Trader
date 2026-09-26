"""SQLAlchemy ORM models for the Trading212 portfolio dashboard backend."""

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PortfolioSnapshot(Base):
    """A point-in-time snapshot of portfolio value.

    Taken periodically by the scheduler (added in a later task) and used to
    build the equity-curve chart on the dashboard.
    """

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    total_value: Mapped[float] = mapped_column(Float)
    unrealized_profit_loss: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))


class OrderFill(Base):
    """A single executed buy/sell fill, synced from Trading212's order history.

    Only fills of type "TRADE" are stored — corporate-action fills (stock
    splits, stock dividends, spin-offs, etc.) are filtered out during sync
    since they'd corrupt FIFO trade reconstruction if included.
    """

    __tablename__ = "order_fills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(String)
    ticker: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[float] = mapped_column(Float)
    # The price and currency as quoted by Trading212 for the instrument.  Keep
    # these separate from `fill_price`, which is normalized to the account
    # currency for performance calculations.
    source_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    fill_price: Mapped[float] = mapped_column(Float)
    net_value: Mapped[float] = mapped_column(Float)
    realised_profit_loss: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Dividend(Base):
    """A single dividend payment, synced from Trading212's dividend history."""

    __tablename__ = "dividends"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    type: Mapped[str] = mapped_column(String)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HistorySyncState(Base):
    """Tracks completion and resumable cursors for one-time history backfills."""

    __tablename__ = "history_sync_states"

    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    continuation_cursor: Mapped[str | None] = mapped_column(String(64), nullable=True)


class WatchlistEntry(Base):
    """A locally persisted, read-only reference to an Alpaca US equity."""

    __tablename__ = "watchlist_entries"
    __table_args__ = (UniqueConstraint("alpaca_asset_id", name="uq_watchlist_entries_alpaca_asset_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alpaca_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    logo_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    logo_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MarketPriceBar(Base):
    """An immutable raw, consolidated SIP observation for a watched asset."""

    __tablename__ = "market_price_bars"
    __table_args__ = (
        UniqueConstraint(
            "alpaca_asset_id",
            "interval_seconds",
            "starts_at",
            name="uq_market_price_bar",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alpaca_asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[object] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[object] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[object] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[object] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vwap: Mapped[object | None] = mapped_column(Numeric(20, 8), nullable=True)
    session: Mapped[str] = mapped_column(String(16), nullable=False)
    source_feed: Mapped[str] = mapped_column(String(16), nullable=False, default="sip")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MarketCorporateAction(Base):
    """A provider corporate-action record retained beside raw market observations."""

    __tablename__ = "market_corporate_actions"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alpaca_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(48), nullable=False)
    effective_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MarketHistorySyncState(Base):
    """Watermarks for the resumable per-asset SIP-history backfill."""

    __tablename__ = "market_history_sync_states"

    alpaca_asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    five_minute_backfill_cursor: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    five_minute_backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    one_minute_backfill_cursor: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    one_minute_backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_backfill_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sip_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    corporate_actions_backfill_cursor: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    corporate_actions_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NewsSourceItem(Base):
    """A bounded, attributed observation from one external source."""

    __tablename__ = "news_source_items"
    __table_args__ = (UniqueConstraint("provider", "source_key", name="uq_news_source_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    candidate_symbols: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class NewsStory(Base):
    """One source-backed development shown as a single dashboard card."""

    __tablename__ = "news_stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    short_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    relevance_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_facts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unknowns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="unclear")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)


class NewsStorySource(Base):
    __tablename__ = "news_story_sources"

    story_id: Mapped[int] = mapped_column(ForeignKey("news_stories.id"), primary_key=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("news_source_items.id"), primary_key=True)


class NewsStoryStock(Base):
    __tablename__ = "news_story_stocks"

    story_id: Mapped[int] = mapped_column(ForeignKey("news_stories.id"), primary_key=True)
    alpaca_asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)


class MarketEvent(Base):
    """An explicitly dated future development, not a forecast of its outcome."""

    __tablename__ = "market_events"

    event_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    previous_event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_precision: Mapped[str] = mapped_column(String(16), nullable=False)
    date_status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketEventStock(Base):
    __tablename__ = "market_event_stocks"

    event_key: Mapped[str] = mapped_column(ForeignKey("market_events.event_key"), primary_key=True)
    alpaca_asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)


class NewsSyncState(Base):
    __tablename__ = "news_sync_states"

    source_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class NewsAiDailyUsage(Base):
    """Conservative daily reservations and measured OpenAI news token use."""

    __tablename__ = "news_ai_daily_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    reserved_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
