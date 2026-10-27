"""Deterministic swing-trade descriptions from completed, consistently adjusted bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from app.alpaca_market_data import NEW_YORK, HistoricalBar, TradingSession
from app.schemas import AnalysisMetricOut

D = Decimal
ZERO = D(0)
HUNDRED = D(100)
Condition = Literal["supportive", "neutral", "caution", "unavailable"]


def average(values: list[Decimal]) -> Decimal:
    return sum(values, ZERO) / len(values)


def smoothed(values: list[Decimal], period: int, *, exponential: bool = False) -> list[Decimal | None]:
    """Seed with the arithmetic mean; then apply EMA or Wilder smoothing."""
    result: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return result
    previous = average(values[:period])
    result[period - 1] = previous
    alpha = D(2) / (period + 1) if exponential else D(1) / period
    for index in range(period, len(values)):
        previous += alpha * (values[index] - previous)
        result[index] = previous
    return result


@dataclass(frozen=True)
class DailyIndicators:
    ema20: list[Decimal | None]
    sma50: list[Decimal | None]
    rsi: Decimal | None
    atr: list[Decimal | None]
    adx: Decimal | None
    plus_di: Decimal | None
    minus_di: Decimal | None


def daily_indicators(bars: list[HistoricalBar]) -> DailyIndicators:
    closes = [bar.close for bar in bars]
    ema = smoothed(closes, 20, exponential=True)
    sma = [average(closes[i - 49 : i + 1]) if i >= 49 else None for i in range(len(closes))]
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    gains = smoothed([max(change, ZERO) for change in changes], 14)
    losses = smoothed([max(-change, ZERO) for change in changes], 14)
    rsi = None
    if gains and gains[-1] is not None and losses[-1] is not None:
        gain, loss = gains[-1], losses[-1]
        rsi = D(50) if gain == loss else HUNDRED if loss == ZERO else HUNDRED * gain / (gain + loss)
    ranges, plus, minus = [], [], []
    for previous, current in zip(bars, bars[1:]):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
        up, down = current.high - previous.high, previous.low - current.low
        plus.append(up if up > down and up > ZERO else ZERO)
        minus.append(down if down > up and down > ZERO else ZERO)
    atr_values = smoothed(ranges, 14)
    dx: list[Decimal] = []
    plus_di = minus_di = None
    # Directional movement uses the initial 13 differences across 14 bars,
    # then a Wilder update for difference 14. This is the TA-Lib convention;
    # seeding DI with ATR's 14-difference average changes early ADX readings.
    tr, up, down = (sum(items[:13], ZERO) for items in (ranges, plus, minus))
    for current_tr, current_up, current_down in zip(ranges[13:], plus[13:], minus[13:]):
        tr = tr - tr / 14 + current_tr
        up = up - up / 14 + current_up
        down = down - down / 14 + current_down
        plus_di = HUNDRED * up / tr if tr else ZERO
        minus_di = HUNDRED * down / tr if tr else ZERO
        total = plus_di + minus_di
        dx.append(HUNDRED * abs(plus_di - minus_di) / total if total else ZERO)
    adx_values = smoothed(dx, 14)
    return DailyIndicators(
        ema,
        sma,
        rsi,
        [None, *atr_values] if bars else [],
        adx_values[-1] if adx_values else None,
        plus_di,
        minus_di,
    )


def relative_performance(
    bars: list[HistoricalBar], benchmark: list[HistoricalBar], sessions: int
) -> Decimal | None:
    if len(bars) <= sessions:
        return None
    reference = {bar.starts_at.astimezone(NEW_YORK).date(): bar.close for bar in benchmark}
    dates = [bar.starts_at.astimezone(NEW_YORK).date() for bar in bars[-sessions - 1 :]]
    if any(day not in reference for day in dates):
        return None
    return HUNDRED * (bars[-1].close / bars[-sessions - 1].close - reference[dates[-1]] / reference[dates[0]])


def cumulative_rvol(
    bars: list[HistoricalBar],
    calendar: dict[date, TradingSession],
    session_date: date,
    through: datetime,
) -> Decimal | None:
    """Require complete comparable 5-minute grids; never treat missing bars as zero."""
    current = calendar[session_date]
    elapsed = min(through, current.closes_at) - current.opens_at
    if elapsed < timedelta(minutes=5):
        return None
    by_time = {bar.starts_at: bar.volume for bar in bars if valid_bar(bar)}

    def volume(session: TradingSession) -> int | None:
        if session.closes_at - session.opens_at < elapsed:
            return None
        times = [
            session.opens_at + timedelta(minutes=5 * i) for i in range(int(elapsed.total_seconds()) // 300)
        ]
        if any(timestamp not in by_time for timestamp in times):
            return None
        return sum(by_time[timestamp] for timestamp in times)

    current_volume = volume(current)
    # Only the immediately preceding 20 comparable sessions qualify. An outage
    # cannot quietly substitute older, more convenient volume observations.
    prior = [
        session
        for day, session in sorted(calendar.items())
        if day < session_date and session.closes_at - session.opens_at >= elapsed
    ][-20:]
    totals = [volume(session) for session in prior]
    if current_volume is None or len(totals) < 20 or any(value is None for value in totals):
        return None
    denominator = average([D(value) for value in totals if value is not None])
    return D(current_volume) / denominator if denominator > ZERO else None


def valid_bar(bar: HistoricalBar) -> bool:
    prices = [bar.open, bar.high, bar.low, bar.close]
    return (
        all(price.is_finite() and price > ZERO for price in prices)
        and bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
        and bar.volume >= 0
    )


HELP = {
    "ema20": (
        "A 20-session exponential moving average gives recent closing prices more weight.",
        "Shows the recent trend and how far the current price has moved from it.",
        "Bullish: price above both rising averages. Bearish: below both falling averages. "
        "Slope compares today’s average with five sessions earlier; mixed conditions are neutral.",
    ),
    "sma50": (
        "The arithmetic average of the last 50 completed session closes.",
        "Adds broader trend context to a 2–10 day holding period.",
        "Bullish: price above both rising averages. Bearish: below both falling averages. "
        "The average uses completed days; its price distance uses the timestamp shown for price context.",
    ),
    "rsi14": (
        "RSI compares Wilder-smoothed gains and losses over 14 sessions on a 0–100 scale.",
        "Helps distinguish upward momentum, weakness and a stretched move.",
        "Above 50: upward momentum; above 70 also flags overbought conditions, not a reversal. "
        "40–50: neutral; below 40: weak. Below 30 is oversold, not automatically a bargain. "
        "A completely flat history is shown as neutral 50. These are descriptive default bands.",
    ),
    "atr14": (
        "ATR averages 14 sessions of true range, including gaps from the previous close.",
        "Puts normal price fluctuations and possible stop distances in context; it predicts no direction.",
        "The percentage compares ATR with the last close. Above its preceding 126-session 90th "
        "percentile is unusually volatile. ATR stays neutral in colour because it gives no direction.",
    ),
    "adx14": (
        "ADX smooths the difference between positive and negative directional movement over 14 periods.",
        "Helps establish whether a trend is strong enough to give trend-following signals context.",
        "25 or higher: established trend; +DI above −DI is bullish, the reverse bearish. "
        "Below 20: weak; 20–25: developing. A high ADX alone does not indicate a rise.",
    ),
    "rs5": (
        "The stock’s five-session price return minus SPY’s return on the same dates, in percentage points.",
        "Shows whether the stock has recently led or lagged the broad US market.",
        "Positive: outperforming; negative: lagging. Green requires a positive stock return as well "
        "as outperformance; red requires a loss as well as underperformance. Mixed cases are neutral. "
        "These are split-adjusted price returns, excluding dividends.",
    ),
    "rs20": (
        "The stock’s 20-session price return minus SPY’s return on the same dates, in percentage points.",
        "Checks whether recent leadership also exists over roughly a month.",
        "Positive: outperforming; negative: lagging. Green requires a gain plus outperformance; "
        "red requires a loss plus underperformance. Mixed cases are neutral. "
        "Read alongside the five-day comparison. These price returns exclude dividends.",
    ),
    "rvol20": (
        "Regular-session volume so far divided by average volume at the same elapsed time over 20 sessions.",
        "Shows how much participation is behind a move without comparing a partial day to full days.",
        "1× is typical; 1.5× is 50% more activity. At least 1.5× is green on an up day and red on a "
        "down day versus the previous close; otherwise neutral. Volume alone has no direction. "
        "The 1.5× cutoff is a descriptive default; missing volume is never counted as zero.",
    ),
    "extension": (
        "Current price minus the completed-day EMA20, divided by ATR14.",
        "Shows how far price has stretched relative to its normal daily range.",
        "Above +2 ATR flags chasing risk even during an upward trend; this is a default threshold. "
        "The colour stays neutral: extension does not establish a reversal or a buying opportunity.",
    ),
    "range_high": (
        "The highest high in the 20 sessions before the assessed session, with its distance from price.",
        "Provides a recent resistance reference and helps identify possible breakouts.",
        "Within 0.5 ATR below the high: near resistance, not a bearish signal by itself. Above it "
        "with RVOL ≥1.5×: bullish breakout context. These cutoffs are defaults, not profit estimates. "
        "Above the range there is no higher reference in this window.",
    ),
    "range_low": (
        "The lowest daily low in the 20 sessions before the assessed session, with its distance from price.",
        "Provides a recent support reference and highlights a breakdown.",
        "Price below the low is bearish. Above it is neutral: historical support does not guarantee "
        "a bounce. The assessed session is excluded to avoid moving the reference with today’s price.",
    ),
}


def metric(
    key: str,
    label: str,
    value: Decimal | None,
    unit: Literal["usd", "percent", "points", "ratio", "number"],
    basis: Literal["daily", "intraday"],
    condition: Condition = "neutral",
    interpretation: str = "Neutral",
    detail: str = "",
) -> AnalysisMetricOut:
    description, relevance, thresholds = HELP[key]
    return AnalysisMetricOut(
        id=key,
        label=label,
        value=float(value) if value is not None else None,
        unit=unit,
        basis=basis,
        condition=condition if value is not None else "unavailable",
        interpretation=interpretation if value is not None else "Unavailable",
        detail=detail if value is not None else detail or "More completed history is needed.",
        description=description,
        relevance=relevance,
        thresholds=thresholds,
    )


def build_metrics(
    daily: list[HistoricalBar],
    benchmark: list[HistoricalBar],
    price: Decimal | None,
    context_date: date | None,
    rvol: Decimal | None,
) -> list[AnalysisMetricOut]:
    """Return values and explainable descriptive conditions, never a buy/sell score."""
    values = daily_indicators(daily)
    ema = values.ema20[-1] if daily else None
    sma = values.sma50[-1] if daily else None
    atr = values.atr[-1] if daily else None
    close = daily[-1].close if daily else None
    rows: list[AnalysisMetricOut] = []
    slopes = [
        series[-1] - series[-6]
        if len(series) >= 6 and series[-1] is not None and series[-6] is not None
        else None
        for series in (values.ema20, values.sma50)
    ]
    trend: Condition = "neutral"
    trend_label = "Mixed trend"
    if price is not None and ema is not None and sma is not None and all(s is not None for s in slopes):
        if price > max(ema, sma) and all(s > ZERO for s in slopes if s is not None):
            trend, trend_label = "supportive", "Upward trend"
        elif price < min(ema, sma) and all(s < ZERO for s in slopes if s is not None):
            trend, trend_label = "caution", "Downward trend"
    for key, label, value, slope in (
        ("ema20", "20-day EMA", ema, slopes[0]),
        ("sma50", "50-day average", sma, slopes[1]),
    ):
        detail = "Price context unavailable."
        if value is not None and price is not None:
            distance = HUNDRED * (price / value - 1)
            direction = "rising" if slope is not None and slope > ZERO else "falling" if slope else "flat"
            detail = f"Price {distance:+.2f}% vs average"
            detail += f" · average {direction}" if slope is not None else " · slope needs more history"
        rows.append(metric(key, label, value, "usd", "intraday", trend, trend_label, detail))
    rsi = values.rsi
    rsi_condition: Condition = "neutral"
    rsi_label = "Neutral momentum"
    if rsi is not None:
        if rsi < 40:
            rsi_condition, rsi_label = "caution", "Weak momentum · oversold" if rsi < 30 else "Weak momentum"
        elif rsi > 70:
            rsi_condition, rsi_label = "supportive", "Upward momentum · overbought"
        elif rsi > 50:
            rsi_condition, rsi_label = "supportive", "Upward momentum"
    rows.append(metric("rsi14", "RSI · 14 days", rsi, "number", "daily", rsi_condition, rsi_label))
    atr_percent = HUNDRED * atr / close if atr is not None and close else None
    prior_percent = [HUNDRED * a / bar.close for a, bar in zip(values.atr[:-1], daily[:-1]) if a is not None]
    percentile = None
    if len(prior_percent) >= 126:
        ordered = sorted(prior_percent[-126:])
        percentile = (ordered[112] + ordered[113]) / 2  # Linear 90th percentile: (126 - 1) * .9.
    unusual = atr_percent is not None and percentile is not None and atr_percent > percentile
    atr_detail = f"{atr_percent:.2f}% of closing price" if atr_percent is not None else ""
    if atr_percent is not None and percentile is None:
        atr_detail += " · insufficient history for volatility comparison"
    rows.append(
        metric(
            "atr14",
            "Daily range · ATR14",
            atr,
            "usd",
            "daily",
            "neutral",
            "Unusually volatile" if unusual else "Volatility",
            atr_detail,
        )
    )
    adx_condition: Condition = "neutral"
    adx_label = "Weak trend" if values.adx is None or values.adx < 20 else "Developing trend"
    if values.adx is not None and values.adx >= 25:
        if values.plus_di > values.minus_di:
            adx_condition, adx_label = "supportive", "Established upward trend"
        elif values.minus_di > values.plus_di:
            adx_condition, adx_label = "caution", "Established downward trend"
        else:
            adx_label = "Balanced direction"
    di_detail = f"+DI {values.plus_di:.1f} · −DI {values.minus_di:.1f}" if values.plus_di is not None else ""
    rows.append(
        metric(
            "adx14",
            "Trend strength · ADX14",
            values.adx,
            "number",
            "daily",
            adx_condition,
            adx_label,
            di_detail,
        )
    )
    for sessions in (5, 20):
        relative = relative_performance(daily, benchmark, sessions)
        condition: Condition = "neutral"
        label = "Matching SPY"
        detail = "Matching stock and SPY history is required."
        if relative is not None:
            stock_return = HUNDRED * (daily[-1].close / daily[-sessions - 1].close - 1)
            benchmark_return = stock_return - relative
            label = "Outperforming SPY" if relative > ZERO else "Lagging SPY" if relative < ZERO else label
            if relative > ZERO and stock_return > ZERO:
                condition = "supportive"
            elif relative < ZERO and stock_return < ZERO:
                condition = "caution"
            detail = f"Stock {stock_return:+.2f}% · SPY {benchmark_return:+.2f}%"
        rows.append(
            metric(
                f"rs{sessions}",
                f"Vs market · {sessions} days",
                relative,
                "points",
                "daily",
                condition,
                label,
                detail,
            )
        )
    prior_bars = [
        bar for bar in daily if context_date and bar.starts_at.astimezone(NEW_YORK).date() < context_date
    ]
    previous = prior_bars[-1].close if prior_bars else None
    volume_condition: Condition = "neutral"
    volume_label = "Typical participation" if rvol is not None and rvol >= D("0.8") else "Light participation"
    if rvol is not None and rvol >= D("1.5"):
        volume_label = "High participation"
        if price is not None and previous is not None and price != previous:
            volume_condition = "supportive" if price > previous else "caution"
            volume_label = "High volume on up day" if price > previous else "High volume on down day"
    rows.append(
        metric(
            "rvol20",
            "Relative volume · 20 days",
            rvol,
            "ratio",
            "intraday",
            volume_condition,
            volume_label,
            "20 complete comparable sessions of volume are required." if rvol is None else "",
        )
    )
    extension = (price - ema) / atr if price is not None and ema is not None and atr else None
    stretched = extension is not None and extension > 2
    rows.append(
        metric(
            "extension",
            "Distance from EMA20",
            extension,
            "ratio",
            "intraday",
            "neutral",
            "Extended above trend" if stretched else "Trend distance",
            "Measured in ATR units." if extension is not None else "A non-zero ATR and price are required.",
        )
    )
    high = max(bar.high for bar in prior_bars[-20:]) if len(prior_bars) >= 20 else None
    low = min(bar.low for bar in prior_bars[-20:]) if len(prior_bars) >= 20 else None
    near = price is not None and high is not None and atr is not None and ZERO <= high - price <= atr / 2
    breakout = price is not None and high is not None and price > high
    supported = breakout and rvol is not None and rvol >= D("1.5")
    high_detail = f"{HUNDRED * (high / price - 1):+.2f}% from price" if high is not None and price else ""
    if breakout:
        high_detail += " · no higher reference in this window"
    rows.append(
        metric(
            "range_high",
            "Prior 20-session high",
            high,
            "usd",
            "intraday",
            "supportive" if supported else "neutral",
            "Near resistance"
            if near
            else "Breakout with volume"
            if supported
            else ("Above recent range" if breakout else "Resistance reference"),
            high_detail,
        )
    )
    breakdown = price is not None and low is not None and price < low
    low_detail = f"{HUNDRED * (low / price - 1):+.2f}% from price" if low is not None and price else ""
    rows.append(
        metric(
            "range_low",
            "Prior 20-session low",
            low,
            "usd",
            "intraday",
            "caution" if breakdown else "neutral",
            "Below support" if breakdown else "Support reference",
            low_detail,
        )
    )
    return rows
