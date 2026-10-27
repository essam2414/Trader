"""Reference arithmetic and descriptive boundaries for swing analysis."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.alpaca_market_data import NEW_YORK, HistoricalBar, TradingSession
from app.services.stock_analysis import build_metrics, cumulative_rvol, daily_indicators, relative_performance

D = Decimal


def bar(day, close, high=None, low=None, volume=100):
    value = D(str(close))
    return HistoricalBar(
        starts_at=day,
        open=value,
        high=D(str(high)) if high is not None else value + 1,
        low=D(str(low)) if low is not None else value - 1,
        close=value,
        volume=volume,
        trade_count=None,
        vwap=None,
    )


def history(closes):
    return [
        bar(datetime(2025, 1, 1, tzinfo=NEW_YORK) + timedelta(days=i), close)
        for i, close in enumerate(closes)
    ]


def by_id(rows):
    return {row.id: row for row in rows}


def oscillating_history(count):
    """Deterministic OHLC input with gaps and changing directional movement."""
    result = []
    for i in range(count):
        close = D(100) + D("0.17") * i + D("0.83") * ((i * 7) % 13 - 6) + D(7) * ((i // 17) % 2)
        opening = close + D("0.13") * ((i * 3) % 9 - 4)
        high = max(opening, close) + D("0.4") * (i % 5 + 1)
        low = min(opening, close) - D("0.3") * (i % 7 + 1)
        result.append(
            HistoricalBar(
                datetime(2025, 1, 1, tzinfo=NEW_YORK) + timedelta(days=i),
                opening,
                high,
                low,
                close,
                1000 + i * 10,
                None,
                None,
            )
        )
    return result


# Independently generated with TA-Lib Python 0.6.8 / C library 0.6.4.
# Columns: EMA20, SMA50, RSI14, ATR14, ADX14, +DI14, -DI14.
# Keep the numbers as fixtures so tests don't require TA-Lib at runtime.
@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (15, [None, None, 55.42168674698795, 6.91, None, 44.60208869859225, 36.33419177476182]),
        (
            20,
            [
                102.167,
                None,
                56.52647236527184,
                6.682038733860891,
                None,
                46.072745631569525,
                35.41655111578852,
            ],
        ),
        (
            28,
            [
                107.337721384003,
                None,
                55.701495120317134,
                6.6951282913310015,
                12.934261078301203,
                44.7861803418702,
                35.17142027227108,
            ],
        ),
        (
            50,
            [
                107.95698220807917,
                106.4454,
                50.0734196055133,
                6.8372095478941475,
                6.472917785131578,
                40.52670874236085,
                39.268933980628404,
            ],
        ),
        (
            166,
            [
                132.0568412024608,
                128.002,
                55.9454059738394,
                6.690231143743047,
                6.831960487062015,
                44.31284401941727,
                36.37661143631355,
            ],
        ),
        (
            250,
            [
                142.18230147133215,
                141.1382,
                47.23418421404879,
                6.891565894250969,
                5.147059872022863,
                37.59512569077344,
                43.3294923175945,
            ],
        ),
    ],
)
def test_indicators_match_independent_reference_from_seed_through_full_warmup(count, expected):
    result = daily_indicators(oscillating_history(count))
    actual = [
        result.ema20[-1],
        result.sma50[-1],
        result.rsi,
        result.atr[-1],
        result.adx,
        result.plus_di,
        result.minus_di,
    ]
    for observed, reference in zip(actual, expected):
        if reference is None:
            assert observed is None
        else:
            assert float(observed) == pytest.approx(reference, abs=1e-10, rel=1e-10)


def test_wilder_rsi_reference_seed_and_recursion():
    closes = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
    ]
    assert float(daily_indicators(history(closes)).rsi) == pytest.approx(70.464135, abs=0.000001)
    assert float(daily_indicators(history([*closes, 46])).rsi) == pytest.approx(66.249619, abs=0.000001)


def test_linear_trend_moving_averages_atr_and_direction_have_known_values():
    result = daily_indicators(history(range(100, 180)))
    assert result.ema20[-1] == D("169.5")
    assert result.sma50[-1] == D("154.5")
    assert result.atr[-1] == 2
    assert result.rsi == 100
    assert result.plus_di == pytest.approx(D(50), abs=D("1e-20"))
    assert result.minus_di == 0
    assert result.adx == 100


def test_atr_includes_overnight_gap_and_wilder_smoothing():
    data = history([100] * 15 + [109])
    assert daily_indicators(data).atr[-1] == D(36) / 14


def test_flat_series_and_short_history_have_no_infinities():
    flat = history([100] * 80)
    flat = [bar(item.starts_at, 100, high=100, low=100) for item in flat]
    values = daily_indicators(flat)
    assert values.rsi == 50
    assert values.atr[-1] == values.adx == 0
    rows = by_id(build_metrics(flat, flat, D(100), date(2025, 4, 1), None))
    assert rows["extension"].value is None
    assert rows["adx14"].condition == "neutral"
    assert all(row.value is None for row in build_metrics([], [], None, None, None))
    assert daily_indicators(history([100] * 14)).rsi is None
    assert daily_indicators(history([100] * 27)).adx is None


def test_relative_strength_is_percentage_points_and_requires_matching_dates():
    stock, benchmark = history([100, 102, 104, 106, 108, 110]), history([100, 101, 102, 103, 104, 105])
    assert relative_performance(stock, benchmark, 5) == 5
    assert relative_performance(stock, benchmark[1:], 5) is None
    assert relative_performance(stock, [*benchmark[:2], *benchmark[3:]], 5) is None


def test_direction_volume_extension_and_range_conditions():
    stock = history(range(100, 180))
    rows = by_id(build_metrics(stock, stock, D(190), date(2025, 4, 1), D(2)))
    assert rows["ema20"].condition == "supportive"
    assert rows["extension"].condition == "neutral"
    assert rows["range_high"].interpretation == "Breakout with volume"
    assert rows["rvol20"].condition == "supportive"
    assert rows["adx14"].condition == "supportive"
    falling = history(range(180, 100, -1))
    rows = by_id(build_metrics(falling, stock, D(90), date(2025, 4, 1), D(2)))
    assert rows["ema20"].condition == rows["adx14"].condition == "caution"
    assert rows["rvol20"].condition == rows["range_low"].condition == "caution"


def test_range_excludes_assessed_day_and_near_resistance_boundary():
    stock = history([100] * 40)
    stock[-1] = bar(stock[-1].starts_at, 110, high=120, low=90)
    rows = by_id(build_metrics(stock, stock, D(100), stock[-1].starts_at.date(), D("1.49")))
    assert rows["range_high"].value == 101
    assert rows["range_low"].value == 99
    assert rows["range_high"].condition == "neutral"
    rows = by_id(build_metrics(stock, stock, D(102), stock[-1].starts_at.date(), D("1.49")))
    assert rows["range_high"].condition == "neutral"


@pytest.mark.parametrize(("volume", "expected"), [("1.49", "neutral"), ("1.5", "supportive")])
def test_volume_threshold(volume, expected):
    stock = history(range(100, 180))
    rows = by_id(build_metrics(stock, stock, D(190), date(2025, 4, 1), D(volume)))
    assert rows["rvol20"].condition == expected


def volume_fixture():
    calendar, bars = {}, []
    for i in range(21):
        opens = datetime(2026, 9, 1, 9, 30, tzinfo=NEW_YORK) + timedelta(days=i)
        calendar[opens.date()] = TradingSession(opens, opens + timedelta(hours=6, minutes=30))
        for offset in (0, 5):
            bars.append(bar(opens + timedelta(minutes=offset), 100, volume=180 if i == 20 else 100))
        bars.append(bar(opens - timedelta(minutes=5), 100, volume=999999))
    return calendar, bars, opens


def test_rvol_compares_same_time_and_excludes_extended_hours_and_missing_data():
    calendar, bars, opens = volume_fixture()
    through = opens + timedelta(minutes=10)
    assert cumulative_rvol(bars, calendar, opens.date(), through) == D("1.8")
    assert cumulative_rvol(bars[1:], calendar, opens.date(), through) is None
    assert cumulative_rvol(bars, calendar, opens.date(), opens) is None
    empty = [bar(item.starts_at, 100, volume=0) for item in bars]
    assert cumulative_rvol(empty, calendar, opens.date(), through) is None


def test_rvol_does_not_use_a_short_session_beyond_its_close():
    calendar, bars, opens = volume_fixture()
    first = min(calendar)
    session = calendar[first]
    calendar[first] = TradingSession(session.opens_at, session.opens_at + timedelta(minutes=5))
    assert cumulative_rvol(bars, calendar, opens.date(), opens + timedelta(minutes=10)) is None


def test_overbought_rsi_is_upward_momentum_not_a_bearish_reversal_signal():
    stock = history(range(100, 180))
    rows = by_id(build_metrics(stock, stock, D(179), date(2025, 4, 1), D(1)))
    assert rows["rsi14"].value == 100
    assert rows["rsi14"].condition == "supportive"
    assert "overbought" in rows["rsi14"].interpretation.lower()


def test_balanced_rsi_fifty_has_no_direction_even_when_prices_moved():
    stock = history([100, 101, 100] + [100] * 12)
    rows = by_id(build_metrics(stock, stock, D(100), date(2025, 4, 1), None))
    assert rows["rsi14"].value == 50
    assert rows["rsi14"].condition == "neutral"


def test_high_volatility_does_not_imply_downside():
    stock = history([100] * 200)
    stock[-1] = bar(stock[-1].starts_at, 100, high=150, low=50)
    rows = by_id(build_metrics(stock, stock, D(100), date(2026, 1, 1), D(1)))
    assert rows["atr14"].interpretation == "Unusually volatile"
    assert rows["atr14"].condition == "neutral"


@pytest.mark.parametrize(
    ("stock_end", "market_end", "expected"),
    [
        (90, 80, "neutral"),  # Losing less than SPY is not an absolute upward signal.
        (110, 120, "neutral"),  # Gaining less than SPY is not an absolute downward signal.
        (110, 105, "supportive"),
        (90, 95, "caution"),
        (100, 95, "neutral"),
    ],
)
def test_relative_performance_colour_requires_agreement_with_absolute_return(stock_end, market_end, expected):
    stock = history([100] * 20 + [stock_end])
    benchmark = history([100] * 20 + [market_end])
    rows = by_id(build_metrics(stock, benchmark, D(stock_end), date(2026, 1, 1), None))
    for key in ("rs5", "rs20"):
        assert rows[key].condition == expected
        assert "Stock" in rows[key].detail and "SPY" in rows[key].detail
