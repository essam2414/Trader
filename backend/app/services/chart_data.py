"""On-demand chart data with a replaceable historical-data source seam."""

from __future__ import annotations

import time as monotonic_time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from threading import Lock
from typing import Protocol

from app.alpaca_market_data import NEW_YORK, AlpacaMarketDataClient, HistoricalBar
from app.models import WatchlistEntry

SIP_DELAY = timedelta(minutes=15)
CHART_ADJUSTMENT = "split"
MAX_HISTORY_WINDOW = timedelta(days=5 * 366)
ONE_MINUTE = 60
FIFTEEN_MINUTES = 15 * ONE_MINUTE
THIRTY_MINUTES = 30 * ONE_MINUTE
ONE_HOUR = 60 * ONE_MINUTE
SIP_CACHE_TTL_SECONDS = 30
ONE_DAY_HISTORY_LOOKBACK = timedelta(days=14)
ONE_DAY_BAR_COUNT = 24 * ONE_HOUR // FIFTEEN_MINUTES


@dataclass(frozen=True)
class ChartRange:
    name: str
    window: timedelta | None
    alpaca_timeframe: str
    output_interval_seconds: int
    calendar_bucket: str | None = None


CHART_RANGES = {
    # Fetch across closed-market gaps, then display the latest 24 hours of actual bars.
    "1D": ChartRange("1D", ONE_DAY_HISTORY_LOOKBACK, "15Min", FIFTEEN_MINUTES),
    "1W": ChartRange("1W", timedelta(days=7), "30Min", THIRTY_MINUTES),
    "1M": ChartRange("1M", timedelta(days=31), "4Hour", 4 * ONE_HOUR),
    "3M": ChartRange("3M", timedelta(days=93), "1Day", 24 * ONE_HOUR),
    "1Y": ChartRange("1Y", timedelta(days=366), "1Day", 7 * 24 * ONE_HOUR, "week"),
    # Five years of true calendar-month closes keeps MAX detailed enough to
    # inspect while avoiding a decades-long series compressed into the plot.
    "MAX": ChartRange("MAX", MAX_HISTORY_WINDOW, "1Day", 30 * 24 * ONE_HOUR, "month"),
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


@dataclass(frozen=True)
class ChartSnapshot:
    canonical_bars: list[ChartBar]
    provisional_iex_bars: list[ChartBar]
    canonical_through: datetime


class ChartDataSource(Protocol):
    """Seam for supplying chart data without changing the chart route contract."""

    def load_chart(
        self,
        entry: WatchlistEntry,
        chart_range: ChartRange,
        now: datetime,
        include_provisional_iex: bool = True,
    ) -> ChartSnapshot:
        """Return split-adjusted SIP history, optionally bridged with a live IEX tail."""


@dataclass(frozen=True)
class _CachedSIPRange:
    bars: list[ChartBar]
    canonical_through: datetime
    expires_at: float


class AlpacaChartDataSource:
    """Fetch split-adjusted chart history on demand without persisting price bars."""

    def __init__(
        self,
        sip_client: AlpacaMarketDataClient,
        iex_client: AlpacaMarketDataClient,
        sip_cache_ttl_seconds: int = SIP_CACHE_TTL_SECONDS,
    ) -> None:
        self._sip_client = sip_client
        self._iex_client = iex_client
        self._sip_cache_ttl_seconds = sip_cache_ttl_seconds
        self._sip_cache: dict[tuple[str, str], _CachedSIPRange] = {}
        self._cache_lock = Lock()

    def load_chart(
        self,
        entry: WatchlistEntry,
        chart_range: ChartRange,
        now: datetime,
        include_provisional_iex: bool = True,
    ) -> ChartSnapshot:
        """Load cached delayed SIP history and, when requested, the fresh IEX bridge."""
        canonical_bars, canonical_through = self._sip_bars(entry, chart_range, now)
        iex_bars = (
            self._iex_tail(entry, chart_range, canonical_through, now) if include_provisional_iex else []
        )
        if chart_range.name == "1D":
            # Count overlapping SIP/IEX buckets once and preserve their provenance.
            timestamps = sorted({bar.starts_at for bar in [*canonical_bars, *iex_bars]})
            if len(timestamps) > ONE_DAY_BAR_COUNT:
                start = timestamps[-ONE_DAY_BAR_COUNT]
                canonical_bars = [bar for bar in canonical_bars if bar.starts_at >= start]
                iex_bars = [bar for bar in iex_bars if bar.starts_at >= start]
        return ChartSnapshot(canonical_bars, iex_bars, canonical_through)

    def _sip_bars(
        self, entry: WatchlistEntry, chart_range: ChartRange, now: datetime
    ) -> tuple[list[ChartBar], datetime]:
        key = (entry.alpaca_asset_id, chart_range.name)
        current_time = monotonic_time.monotonic()
        with self._cache_lock:
            cached = self._sip_cache.get(key)
            if cached is not None and cached.expires_at > current_time:
                return cached.bars, cached.canonical_through

        canonical_through = _as_utc(now) - SIP_DELAY
        start = canonical_through - chart_range.window if chart_range.window else None
        bars = self._sip_client.get_historical_bars(
            entry.symbol,
            start,
            canonical_through,
            chart_range.alpaca_timeframe,
            adjustment=CHART_ADJUSTMENT,
        )
        chart_bars = aggregate_chart_bars(
            (
                _bar_from_provider(bar, "regular" if chart_range.alpaca_timeframe == "1Day" else None)
                for bar in bars
            ),
            chart_range,
        )
        if chart_range.name == "1D":
            chart_bars = chart_bars[-ONE_DAY_BAR_COUNT:]
        cached = _CachedSIPRange(
            bars=chart_bars,
            canonical_through=canonical_through,
            expires_at=current_time + self._sip_cache_ttl_seconds,
        )
        with self._cache_lock:
            self._sip_cache[key] = cached
        return cached.bars, cached.canonical_through

    def _iex_tail(
        self,
        entry: WatchlistEntry,
        chart_range: ChartRange,
        canonical_through: datetime,
        now: datetime,
    ) -> list[ChartBar]:
        iex_start = min(canonical_through, chart_bucket_start(_as_utc(now), chart_range))
        bars = self._iex_client.get_historical_bars(
            entry.symbol,
            iex_start,
            _as_utc(now),
            "1Min",
            adjustment="raw",
        )
        return aggregate_chart_bars((_bar_from_provider(bar) for bar in bars), chart_range)


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def session_for(timestamp: datetime) -> str:
    """Classify supported US-equity bars without manufacturing no-trade periods."""
    local = _as_utc(timestamp).astimezone(NEW_YORK)
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
    """Aggregate chronological bars without crossing pre-, regular-, or after-hours sessions."""
    grouped: dict[tuple[datetime, str], list[ChartBar]] = {}
    for bar in bars:
        key = (_bucket_start(bar, interval_seconds), bar.session)
        grouped.setdefault(key, []).append(bar)
    return [
        ChartBar(
            starts_at=starts_at,
            open=group[0].open,
            high=max(item.high for item in group),
            low=min(item.low for item in group),
            close=group[-1].close,
            volume=sum(item.volume for item in group),
            session=session,
        )
        for (starts_at, session), group in sorted(grouped.items())
    ]


def chart_bucket_start(timestamp: datetime, chart_range: ChartRange) -> datetime:
    """Return the start of the currently forming output bar for a chart range."""
    if chart_range.calendar_bucket == "day":
        local = _as_utc(timestamp).astimezone(NEW_YORK)
        return datetime.combine(local.date(), time(0), NEW_YORK).astimezone(timezone.utc)
    if chart_range.calendar_bucket == "week":
        local = _as_utc(timestamp).astimezone(NEW_YORK)
        week_start = local.date() - timedelta(days=local.weekday())
        return datetime.combine(week_start, time(4), NEW_YORK).astimezone(timezone.utc)
    if chart_range.calendar_bucket == "month":
        local = _as_utc(timestamp).astimezone(NEW_YORK)
        month_start = local.date().replace(day=1)
        return datetime.combine(month_start, time(4), NEW_YORK).astimezone(timezone.utc)
    session = session_for(timestamp)
    placeholder = ChartBar(timestamp, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 0, session)
    return _bucket_start(placeholder, chart_range.output_interval_seconds)


def aggregate_chart_bars(bars: Iterable[ChartBar], chart_range: ChartRange) -> list[ChartBar]:
    """Aggregate provider bars into the selected chart resolution."""
    if chart_range.calendar_bucket is None:
        return aggregate_bars(bars, chart_range.output_interval_seconds)
    grouped: dict[datetime, list[ChartBar]] = {}
    for bar in bars:
        bucket = chart_bucket_start(bar.starts_at, chart_range)
        grouped.setdefault(bucket, []).append(bar)
    return [
        ChartBar(
            starts_at=starts_at,
            open=group[0].open,
            high=max(item.high for item in group),
            low=min(item.low for item in group),
            close=group[-1].close,
            volume=sum(item.volume for item in group),
            session="regular",
        )
        for starts_at, group in sorted(grouped.items())
    ]
