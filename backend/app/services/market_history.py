"""Canonical raw SIP history and temporary chart-tail assembly."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alpaca_market_data import NEW_YORK, AlpacaMarketDataClient, HistoricalBar
from app.models import MarketCorporateAction, MarketHistorySyncState, MarketPriceBar, WatchlistEntry

SIP_DELAY = timedelta(minutes=15)
FIVE_MINUTES = 300
ONE_MINUTE = 60
FIVE_MINUTE_BACKFILL_SLICE = timedelta(days=90)
ONE_MINUTE_BACKFILL_SLICE = timedelta(days=7)
DAILY_BACKFILL_SLICE = timedelta(days=365)
CORPORATE_ACTIONS_BACKFILL_SLICE = timedelta(days=365)


@dataclass(frozen=True)
class ChartRange:
    name: str
    window: timedelta
    source_interval_seconds: int
    output_interval_seconds: int


CHART_RANGES = {
    "1D": ChartRange("1D", timedelta(days=1), ONE_MINUTE, ONE_MINUTE),
    "1W": ChartRange("1W", timedelta(days=7), FIVE_MINUTES, FIVE_MINUTES),
    "1M": ChartRange("1M", timedelta(days=31), FIVE_MINUTES, 15 * ONE_MINUTE),
    "3M": ChartRange("3M", timedelta(days=93), FIVE_MINUTES, 30 * ONE_MINUTE),
    "1Y": ChartRange("1Y", timedelta(days=366), FIVE_MINUTES, 60 * ONE_MINUTE),
}


@dataclass(frozen=True)
class ChartBar:
    starts_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    session: str


def _as_utc(timestamp: datetime) -> datetime:
    """Treat SQLite's offset-less UTC values as UTC at the persistence boundary."""
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def session_for(timestamp: datetime) -> str:
    """Classify supported US equity bars without manufacturing no-trade periods."""
    local = timestamp.astimezone(NEW_YORK)
    clock = local.timetz().replace(tzinfo=None)
    if time(9, 30) <= clock < time(16):
        return "regular"
    if time(4) <= clock < time(9, 30):
        return "pre_market"
    if time(16) <= clock < time(20):
        return "after_hours"
    return "overnight"


def _bar_from_provider(bar: HistoricalBar, session: str | None = None) -> ChartBar:
    starts_at = _as_utc(bar.starts_at)
    return ChartBar(
        starts_at=starts_at,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        session=session or session_for(starts_at),
    )


def _bar_from_model(bar: MarketPriceBar) -> ChartBar:
    return ChartBar(
        starts_at=_as_utc(bar.starts_at),
        open=Decimal(str(bar.open)),
        high=Decimal(str(bar.high)),
        low=Decimal(str(bar.low)),
        close=Decimal(str(bar.close)),
        volume=bar.volume,
        session=bar.session,
    )


def _bucket_start(bar: ChartBar, interval_seconds: int) -> datetime:
    local = bar.starts_at.astimezone(NEW_YORK)
    if bar.session == "pre_market":
        anchor = datetime.combine(local.date(), time(4), NEW_YORK)
    elif bar.session == "regular":
        anchor = datetime.combine(local.date(), time(9, 30), NEW_YORK)
    elif bar.session == "after_hours":
        anchor = datetime.combine(local.date(), time(16), NEW_YORK)
    else:
        anchor = datetime.combine(local.date(), time(20), NEW_YORK)
    offset_seconds = int((local - anchor).total_seconds())
    return (anchor + timedelta(seconds=(offset_seconds // interval_seconds) * interval_seconds)).astimezone(
        timezone.utc
    )


def aggregate_bars(bars: Iterable[ChartBar], interval_seconds: int) -> list[ChartBar]:
    """Aggregate a sorted intraday series without crossing market-session boundaries."""
    grouped: dict[tuple[datetime, str], list[ChartBar]] = {}
    for bar in bars:
        key = (_bucket_start(bar, interval_seconds), bar.session)
        grouped.setdefault(key, []).append(bar)
    result: list[ChartBar] = []
    for (starts_at, session), group in sorted(grouped.items()):
        result.append(
            ChartBar(
                starts_at=starts_at,
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=sum(item.volume for item in group),
                session=session,
            )
        )
    return result


def upsert_raw_bars(
    db: Session,
    entry: WatchlistEntry,
    bars: Iterable[HistoricalBar],
    interval_seconds: int,
) -> None:
    """Persist raw SIP values only; corrected provider bars update their original key."""
    for bar in bars:
        existing = db.scalar(
            select(MarketPriceBar).where(
                MarketPriceBar.alpaca_asset_id == entry.alpaca_asset_id,
                MarketPriceBar.interval_seconds == interval_seconds,
                MarketPriceBar.starts_at == bar.starts_at,
            )
        )
        values = {
            "symbol": entry.symbol,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "trade_count": bar.trade_count,
            "vwap": bar.vwap,
            "session": session_for(bar.starts_at),
            "source_feed": "sip",
            "ingested_at": datetime.now(timezone.utc),
        }
        if existing is None:
            db.add(
                MarketPriceBar(
                    alpaca_asset_id=entry.alpaca_asset_id,
                    interval_seconds=interval_seconds,
                    starts_at=bar.starts_at,
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    db.commit()


def ensure_sync_state(db: Session, asset_id: str) -> MarketHistorySyncState:
    state = db.get(MarketHistorySyncState, asset_id)
    if state is None:
        state = MarketHistorySyncState(alpaca_asset_id=asset_id)
        db.add(state)
        db.commit()
    return state


def _sync_sip_window(
    db: Session,
    entry: WatchlistEntry,
    sip_client: AlpacaMarketDataClient,
    start: datetime,
    end: datetime,
    interval_seconds: int,
) -> list[ChartBar]:
    timeframe = "1Min" if interval_seconds == ONE_MINUTE else "5Min"
    bars = sip_client.get_historical_bars(entry.symbol, start, end, timeframe, adjustment="raw")
    upsert_raw_bars(db, entry, bars, interval_seconds)
    return [_bar_from_provider(bar) for bar in bars]


def canonical_chart_bars(
    db: Session,
    entry: WatchlistEntry,
    sip_client: AlpacaMarketDataClient,
    chart_range: ChartRange,
    now: datetime,
) -> tuple[list[ChartBar], datetime]:
    """Read canonical SIP bars, using bounded read-through fetching for a new page."""
    canonical_end = _as_utc(now) - SIP_DELAY
    start = _as_utc(now) - chart_range.window
    rows = list(
        db.scalars(
            select(MarketPriceBar)
            .where(
                MarketPriceBar.alpaca_asset_id == entry.alpaca_asset_id,
                MarketPriceBar.interval_seconds == chart_range.source_interval_seconds,
                MarketPriceBar.starts_at >= start,
                MarketPriceBar.starts_at <= canonical_end,
            )
            .order_by(MarketPriceBar.starts_at)
        )
    )
    expected_gap = timedelta(seconds=chart_range.source_interval_seconds * 3)
    latest_starts_at = _as_utc(rows[-1].starts_at) if rows else None
    if latest_starts_at is None or canonical_end - latest_starts_at > expected_gap:
        fetch_start = max(start, latest_starts_at - expected_gap) if latest_starts_at else start
        _sync_sip_window(
            db, entry, sip_client, fetch_start, canonical_end, chart_range.source_interval_seconds
        )
        rows = list(
            db.scalars(
                select(MarketPriceBar)
                .where(
                    MarketPriceBar.alpaca_asset_id == entry.alpaca_asset_id,
                    MarketPriceBar.interval_seconds == chart_range.source_interval_seconds,
                    MarketPriceBar.starts_at >= start,
                    MarketPriceBar.starts_at <= canonical_end,
                )
                .order_by(MarketPriceBar.starts_at)
            )
        )
    return aggregate_bars(
        (_bar_from_model(row) for row in rows), chart_range.output_interval_seconds
    ), canonical_end


def provisional_iex_bars(
    entry: WatchlistEntry,
    iex_client: AlpacaMarketDataClient,
    canonical_end: datetime,
    chart_range: ChartRange,
    now: datetime,
) -> list[ChartBar]:
    """Fetch a visible, ephemeral IEX tail so opening the page has no delay hole."""
    bars = iex_client.get_historical_bars(entry.symbol, canonical_end, now, "1Min", adjustment="raw")
    return aggregate_bars((_bar_from_provider(bar) for bar in bars), chart_range.output_interval_seconds)


def _action_records(payload: dict) -> Iterable[tuple[str, dict]]:
    for action_type, records in payload.items():
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict) and record.get("id"):
                    yield action_type.removesuffix("s"), record


def sync_corporate_actions(
    db: Session,
    entry: WatchlistEntry,
    sip_client: AlpacaMarketDataClient,
    start: date,
    end: date,
) -> None:
    for action_type, record in _action_records(sip_client.get_corporate_actions(entry.symbol, start, end)):
        action = db.get(MarketCorporateAction, str(record["id"]))
        if action is None:
            action = MarketCorporateAction(
                provider_id=str(record["id"]), symbol=entry.symbol, action_type=action_type, raw_data={}
            )
            db.add(action)
        action.alpaca_asset_id = entry.alpaca_asset_id
        action.symbol = str(record.get("symbol", entry.symbol))
        action.action_type = action_type
        action.effective_date = record.get("ex_date") or record.get("process_date")
        action.raw_data = record
    db.commit()


def sync_asset_history(
    db: Session, entry: WatchlistEntry, sip_client: AlpacaMarketDataClient, now: datetime | None = None
) -> None:
    """Advance bounded, resumable backfills before maintaining the rolling SIP edge."""
    as_of = now or datetime.now(timezone.utc)
    canonical_end = as_of - SIP_DELAY
    state = ensure_sync_state(db, entry.alpaca_asset_id)
    if state.five_minute_backfilled_at is None:
        five_minute_start = state.five_minute_backfill_cursor or canonical_end - timedelta(days=365 * 5)
        five_minute_end = min(five_minute_start + FIVE_MINUTE_BACKFILL_SLICE, canonical_end)
        _sync_sip_window(db, entry, sip_client, five_minute_start, five_minute_end, FIVE_MINUTES)
        state.five_minute_backfill_cursor = five_minute_end
        if five_minute_end >= canonical_end:
            state.five_minute_backfilled_at = as_of
    if state.daily_backfilled_at is None:
        daily_start = state.daily_backfill_cursor or canonical_end - timedelta(days=365 * 10)
        daily_end = min(daily_start + DAILY_BACKFILL_SLICE, canonical_end)
        daily_bars = sip_client.get_historical_bars(
            entry.symbol, daily_start, daily_end, "1Day", adjustment="raw"
        )
        upsert_raw_bars(db, entry, daily_bars, 24 * 60 * 60)
        state.daily_backfill_cursor = daily_end
        if daily_end >= canonical_end:
            state.daily_backfilled_at = as_of
    if state.one_minute_backfilled_at is None:
        one_minute_start = state.one_minute_backfill_cursor or canonical_end - timedelta(days=90)
        one_minute_end = min(one_minute_start + ONE_MINUTE_BACKFILL_SLICE, canonical_end)
        _sync_sip_window(db, entry, sip_client, one_minute_start, one_minute_end, ONE_MINUTE)
        state.one_minute_backfill_cursor = one_minute_end
        if one_minute_end >= canonical_end:
            state.one_minute_backfilled_at = as_of
    else:
        _sync_sip_window(
            db, entry, sip_client, canonical_end - timedelta(minutes=30), canonical_end, ONE_MINUTE
        )
    if state.five_minute_backfilled_at is not None:
        _sync_sip_window(
            db, entry, sip_client, canonical_end - timedelta(minutes=30), canonical_end, FIVE_MINUTES
        )
    if state.corporate_actions_synced_at is None:
        actions_start = state.corporate_actions_backfill_cursor or canonical_end - timedelta(days=365 * 10)
        actions_end = min(actions_start + CORPORATE_ACTIONS_BACKFILL_SLICE, canonical_end)
        sync_corporate_actions(db, entry, sip_client, actions_start.date(), actions_end.date())
        state.corporate_actions_backfill_cursor = actions_end
        if actions_end >= canonical_end:
            state.corporate_actions_synced_at = as_of
    else:
        sync_corporate_actions(
            db,
            entry,
            sip_client,
            (canonical_end - timedelta(days=14)).date(),
            canonical_end.date(),
        )
    state.last_sip_sync_at = as_of
    db.commit()
