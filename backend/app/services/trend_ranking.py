"""Describe recent upward price trends from regular-session chart closes."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .chart_data import ChartBar, ChartRange

NEW_YORK = ZoneInfo("America/New_York")
MIN_TRADING_DAYS = 10
RECENT_DAYS = 5
MAX_AGE = timedelta(days=7)
TREND_CHART_RANGE = ChartRange("TREND_1M", timedelta(days=31), "1Day", 24 * 60 * 60, "day")


@dataclass(frozen=True)
class TrendMetrics:
    score: float
    week_trend_percent: float
    month_recovery_percent: float
    rising_sessions: int
    as_of: datetime


def calculate_trend(bars: list[ChartBar], now: datetime) -> TrendMetrics | None:
    """Score one canonical one-month chart; return None for unusable history."""
    daily: dict[date, ChartBar] = {}
    for bar in sorted(bars, key=lambda item: item.starts_at):
        if bar.session != "regular" or not bar.close.is_finite() or bar.close <= Decimal(0):
            continue
        daily[bar.starts_at.astimezone(NEW_YORK).date()] = bar

    closes = list(daily.values())
    if len(closes) < MIN_TRADING_DAYS or now - closes[-1].starts_at > MAX_AGE:
        return None

    recent = [float(bar.close) for bar in closes[-RECENT_DAYS:]]
    log_prices = [math.log(price) for price in recent]
    slopes = [
        (log_prices[end] - log_prices[start]) / (end - start)
        for start in range(RECENT_DAYS)
        for end in range(start + 1, RECENT_DAYS)
    ]
    week_trend = math.expm1(statistics.median(slopes) * (RECENT_DAYS - 1)) * 100
    lowest_close = min(bar.close for bar in closes)
    recovery = float((closes[-1].close / lowest_close - 1) * 100)
    rising = sum(current > previous for previous, current in zip(recent, recent[1:]))

    score = 60 * _clamp(week_trend / 10) + 25 * _clamp(recovery / 15) + 15 * rising / (RECENT_DAYS - 1)
    return TrendMetrics(score, week_trend, recovery, rising, closes[-1].starts_at)


def trend_sort_key(metrics: TrendMetrics | None, previous_index: int) -> tuple[float, ...]:
    """Place sustained rises first, then falling and unavailable stocks."""
    if metrics is None:
        return (2, 0, 0, previous_index)
    if metrics.week_trend_percent > 0:
        return (0, -metrics.score, -metrics.week_trend_percent, previous_index)
    return (1, -metrics.week_trend_percent, -metrics.score, previous_index)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
