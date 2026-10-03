"""Trend ranking uses sustained regular-session movement and tolerates missing history."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.alpaca_market_data import HistoricalBar
from app.config import settings
from app.dependencies import get_chart_data_source
from app.main import app
from app.models import WatchlistEntry
from app.services.chart_data import AlpacaChartDataSource, ChartBar, ChartSnapshot
from app.services.trend_ranking import TREND_CHART_RANGE, calculate_trend, trend_sort_key


def bars_for(closes: list[int], *, session: str = "regular", start: datetime | None = None) -> list[ChartBar]:
    start = start or datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
    return [
        ChartBar(
            start + timedelta(days=index),
            Decimal(price),
            Decimal(price),
            Decimal(price),
            Decimal(price),
            1000,
            session,
        )
        for index, price in enumerate(closes)
    ]


NOW = datetime(2026, 9, 17, 20, tzinfo=timezone.utc)


def test_sustained_rise_beats_one_session_spike():
    steady = calculate_trend(bars_for([90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101]), NOW)
    spike = calculate_trend(bars_for([90, 91, 92, 93, 94, 95, 96, 96, 96, 96, 96, 110]), NOW)

    assert steady is not None and spike is not None
    assert steady.week_trend_percent > 0
    assert spike.week_trend_percent == 0
    assert trend_sort_key(steady, 1) < trend_sort_key(spike, 0)


def test_rebound_can_rank_even_while_below_month_start():
    rebound = calculate_trend(bars_for([120, 116, 110, 104, 96, 88, 80, 82, 84, 87, 90, 94]), NOW)

    assert rebound is not None
    assert rebound.week_trend_percent > 0
    assert rebound.month_recovery_percent > 15
    assert rebound.score > 0


def test_falling_recovery_ranks_below_rising_stock_and_missing_data():
    rising = calculate_trend(bars_for([100, 100, 100, 100, 100, 100, 100, 101, 102, 103, 104, 105]), NOW)
    falling = calculate_trend(bars_for([80, 85, 90, 100, 110, 115, 120, 119, 118, 117, 116, 115]), NOW)

    assert rising is not None and falling is not None
    assert trend_sort_key(rising, 1) < trend_sort_key(falling, 0) < trend_sort_key(None, 2)


def test_ignores_extended_hours_and_rejects_sparse_or_stale_history():
    regular = bars_for([100] * 11 + [101])
    extended = bars_for([500] * 12, session="after_hours")

    assert calculate_trend(regular + extended, NOW) == calculate_trend(regular, NOW)
    assert calculate_trend(regular[:9], NOW) is None
    assert calculate_trend(regular, NOW + timedelta(days=10)) is None


def test_as_of_identifies_the_latest_price_session():
    regular = bars_for([100] * 11 + [101])
    result = calculate_trend(regular, NOW)

    assert result is not None
    assert result.as_of == regular[-1].starts_at


def test_ranking_source_uses_daily_split_adjusted_sip_without_iex():
    class RecordingClient:
        def __init__(self, bars):
            self.bars = bars
            self.calls: list[tuple[str, str]] = []

        def get_historical_bars(self, _symbol, _start, _end, timeframe, adjustment):
            self.calls.append((timeframe, adjustment))
            return self.bars

    daily_bar = HistoricalBar(
        datetime(2026, 9, 11, 4, tzinfo=timezone.utc),
        Decimal("100"),
        Decimal("101"),
        Decimal("99"),
        Decimal("100"),
        1000,
        10,
        None,
    )
    sip = RecordingClient([daily_bar])
    iex = RecordingClient([])
    source = AlpacaChartDataSource(sip, iex)
    entry = WatchlistEntry(alpaca_asset_id="up", symbol="UP", name="Up", exchange="NASDAQ")

    snapshot = source.load_chart(entry, TREND_CHART_RANGE, NOW, include_provisional_iex=False)

    assert sip.calls == [("1Day", "split")]
    assert iex.calls == []
    assert snapshot.canonical_bars[0].starts_at == daily_bar.starts_at
    assert snapshot.canonical_bars[0].session == "regular"
    assert snapshot.provisional_iex_bars == []


class FakeTrendSource:
    def __init__(self):
        self.ranges: list[tuple[str, str, bool]] = []

    def load_chart(self, entry, chart_range, now, include_provisional_iex=True):
        self.ranges.append((chart_range.name, chart_range.alpaca_timeframe, include_provisional_iex))
        closes = [100] * 7 + ([100, 101, 102, 103, 104] if entry.symbol == "UP" else [100, 99, 98, 97, 96])
        start = now - timedelta(days=len(closes))
        return ChartSnapshot(bars_for(closes, start=start), [], now - timedelta(minutes=15))


def test_rank_route_uses_one_month_canonical_history_and_preserves_watchlist(client, db_session):
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="down", symbol="DOWN", name="Down", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="up", symbol="UP", name="Up", exchange="NASDAQ"),
        ]
    )
    db_session.commit()
    source = FakeTrendSource()
    app.dependency_overrides[get_chart_data_source] = lambda: source

    response = client.get(
        "/api/watchlist/trends/rank?assetIds=down,up",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert [item["assetId"] for item in response.json()] == ["up", "down"]
    assert all(item["status"] == "ready" for item in response.json())
    assert source.ranges == [("TREND_1M", "1Day", False)] * 2
    assert db_session.query(WatchlistEntry).count() == 2


def test_rank_route_places_missing_history_last_without_dropping_the_stock(client, db_session):
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="missing", symbol="MISSING", name="Missing", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="up", symbol="UP", name="Up", exchange="NASDAQ"),
        ]
    )
    db_session.commit()

    class PartialTrendSource(FakeTrendSource):
        def load_chart(self, entry, chart_range, now, include_provisional_iex=True):
            if entry.symbol == "MISSING":
                return ChartSnapshot([], [], now - timedelta(minutes=15))
            return super().load_chart(entry, chart_range, now, include_provisional_iex)

    app.dependency_overrides[get_chart_data_source] = lambda: PartialTrendSource()
    response = client.get(
        "/api/watchlist/trends/rank?assetIds=missing,up",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert [(item["assetId"], item["status"]) for item in response.json()] == [
        ("up", "ready"),
        ("missing", "insufficient_history"),
    ]
