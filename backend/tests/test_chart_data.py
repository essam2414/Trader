"""On-demand Alpaca chart data and its replaceable source seam."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.alpaca_market_data import NEW_YORK, HistoricalBar
from app.config import settings
from app.dependencies import get_chart_data_source, get_trading212_client
from app.main import app
from app.models import MarketPriceBar, WatchlistEntry
from app.services.chart_data import (
    CHART_RANGES,
    MAX_HISTORY_WINDOW,
    AlpacaChartDataSource,
    ChartBar,
    ChartSnapshot,
    aggregate_chart_bars,
)


@pytest.mark.parametrize(
    ("range_name", "timeframe"),
    [("1D", "15Min"), ("1W", "30Min"), ("1M", "4Hour"), ("3M", "1Day"), ("1Y", "1Day"), ("MAX", "1Day")],
)
def test_chart_range_uses_its_native_alpaca_timeframe(range_name, timeframe):
    sip_client = RecordingMarketDataClient()
    iex_client = RecordingMarketDataClient()
    source = AlpacaChartDataSource(sip_client, iex_client)

    source.load_chart(watchlist_entry(), CHART_RANGES[range_name], chart_now())

    assert sip_client.calls[0]["timeframe"] == timeframe
    assert iex_client.calls[0]["timeframe"] == "1Min"


@pytest.mark.parametrize("range_name", ["1D", "1W", "1M", "3M", "1Y", "MAX"])
def test_chart_ranges_request_split_adjusted_sip_history(range_name):
    sip_client = RecordingMarketDataClient()
    iex_client = RecordingMarketDataClient()
    source = AlpacaChartDataSource(sip_client, iex_client)

    source.load_chart(watchlist_entry(), CHART_RANGES[range_name], chart_now())

    assert sip_client.calls[0]["adjustment"] == "split"
    assert iex_client.calls[0]["adjustment"] == "raw"


def test_one_day_chart_outputs_fifteen_minute_sip_closes():
    sip_bars = [
        historical_bar(datetime(2026, 9, 23, 14, minute, tzinfo=timezone.utc), Decimal("200") + minute)
        for minute in range(15)
    ]
    source = AlpacaChartDataSource(
        RecordingMarketDataClient(bars=sip_bars),
        RecordingMarketDataClient(bars=[]),
    )

    chart = source.load_chart(watchlist_entry(), CHART_RANGES["1D"], chart_now())

    assert len(chart.canonical_bars) == 1
    assert chart.canonical_bars[0].starts_at == sip_bars[0].starts_at
    assert chart.canonical_bars[0].close == sip_bars[-1].close


def test_one_day_chart_outputs_fifteen_minute_iex_tail_closes():
    iex_bars = [
        historical_bar(datetime(2026, 9, 23, 15, 45 + minute, tzinfo=timezone.utc), Decimal("300") + minute)
        for minute in range(15)
    ]
    source = AlpacaChartDataSource(
        RecordingMarketDataClient(bars=[]),
        RecordingMarketDataClient(bars=iex_bars),
    )

    chart = source.load_chart(watchlist_entry(), CHART_RANGES["1D"], chart_now())

    assert len(chart.provisional_iex_bars) == 1
    assert chart.provisional_iex_bars[0].starts_at == iex_bars[0].starts_at
    assert chart.provisional_iex_bars[0].close == iex_bars[-1].close


def test_max_chart_requests_five_year_history_and_returns_monthly_bars():
    sip_client = RecordingMarketDataClient()
    iex_client = RecordingMarketDataClient()
    source = AlpacaChartDataSource(sip_client, iex_client)

    source.load_chart(watchlist_entry(), CHART_RANGES["MAX"], chart_now())

    assert sip_client.calls[0]["start"] == chart_now() - timedelta(minutes=15) - MAX_HISTORY_WINDOW
    assert CHART_RANGES["MAX"].output_interval_seconds == 30 * 24 * 60 * 60
    assert CHART_RANGES["MAX"].calendar_bucket == "month"


def test_chart_source_caches_sip_history_but_refreshes_the_iex_tail():
    sip_client = RecordingMarketDataClient()
    iex_client = RecordingMarketDataClient()
    source = AlpacaChartDataSource(sip_client, iex_client)

    first = source.load_chart(watchlist_entry(), CHART_RANGES["1D"], chart_now())
    second = source.load_chart(watchlist_entry(), CHART_RANGES["1D"], chart_now())

    assert len(sip_client.calls) == 1
    assert len(iex_client.calls) == 2
    assert first.canonical_bars == second.canonical_bars
    assert first.provisional_iex_bars == second.provisional_iex_bars


def test_chart_source_keeps_iex_bars_out_of_the_sip_history():
    sip_client = RecordingMarketDataClient(close="200")
    iex_client = RecordingMarketDataClient(close="201")
    source = AlpacaChartDataSource(sip_client, iex_client)

    chart = source.load_chart(watchlist_entry(), CHART_RANGES["1D"], chart_now())

    assert [bar.close for bar in chart.canonical_bars] == [Decimal("200")]
    assert [bar.close for bar in chart.provisional_iex_bars] == [Decimal("201")]


@pytest.mark.parametrize(
    ("range_name", "timestamps", "expected_count"),
    [
        ("1Y", ["2026-09-21T04:00:00-04:00", "2026-09-22T04:00:00-04:00"], 1),
        ("MAX", ["2026-08-31T04:00:00-04:00", "2026-09-01T04:00:00-04:00"], 2),
    ],
)
def test_calendar_chart_ranges_aggregate_daily_bars(range_name, timestamps, expected_count):
    bars = [
        ChartBar(
            starts_at=datetime.fromisoformat(timestamp).astimezone(NEW_YORK),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=10,
            session="regular",
        )
        for timestamp in timestamps
    ]

    result = aggregate_chart_bars(bars, CHART_RANGES[range_name])

    assert len(result) == expected_count
    assert all(bar.session == "regular" for bar in result)


def test_chart_route_keeps_its_response_contract_without_writing_price_bars(client, db_session):
    entry = watchlist_entry()
    db_session.add(entry)
    db_session.commit()
    app.dependency_overrides[get_chart_data_source] = lambda: FakeChartDataSource()

    response = client.get(
        f"/api/watchlist/{entry.alpaca_asset_id}/chart?range=1D",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["intervalSeconds"] == 900
    assert response.json()["canonicalFeed"] == "sip"
    assert response.json()["adjustment"] == "split"
    assert response.json()["provisionalIexBars"]
    assert db_session.query(MarketPriceBar).count() == 0


def test_position_route_returns_the_open_position_purchase_price_in_the_instrument_currency(
    client, db_session
):
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="SanDisk", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    trading212_client = FakeTrading212Client(
        positions=[
            {
                "instrument": {"ticker": "SNDK_US_EQ", "currency": "USD"},
                "averagePricePaid": 62.75,
            }
        ]
    )
    app.dependency_overrides[get_trading212_client] = lambda: trading212_client

    response = client.get(
        f"/api/watchlist/{entry.alpaca_asset_id}/position",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["purchasePrice"] == 62.75
    assert response.json()["purchasePriceCurrency"] == "USD"
    assert trading212_client.get_positions_calls == 1


def test_position_route_matches_sandisk_trading212_ticker(client, db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="SanDisk", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    app.dependency_overrides[get_trading212_client] = lambda: FakeTrading212Client(
        positions=[
            {
                "instrument": {"ticker": "SNDK1_US_EQ", "currency": "USD"},
                "averagePricePaid": 1744.51,
            }
        ]
    )

    response = client.get(
        f"/api/watchlist/{entry.alpaca_asset_id}/position",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.json() == {"purchasePrice": 1744.51, "purchasePriceCurrency": "USD"}


def test_position_price_is_available_when_market_history_is_unavailable(client, db_session):
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="SanDisk", exchange="NASDAQ")
    db_session.add(entry)
    db_session.commit()
    app.dependency_overrides[get_chart_data_source] = lambda: None
    app.dependency_overrides[get_trading212_client] = lambda: FakeTrading212Client(
        positions=[
            {
                "instrument": {"ticker": "SNDK_US_EQ", "currency": "USD"},
                "averagePricePaid": 62.75,
            }
        ]
    )

    response = client.get(
        f"/api/watchlist/{entry.alpaca_asset_id}/position",
        headers={"Authorization": f"Bearer {settings.dashboard_api_key}"},
    )

    assert response.status_code == 200
    assert response.json() == {"purchasePrice": 62.75, "purchasePriceCurrency": "USD"}


def test_application_does_not_schedule_market_history_ingestion(client):
    scheduled_functions = {job.func.__name__ for job in client.app.state.scheduler.get_jobs()}

    assert "run_market_history_sync_job" not in scheduled_functions


def watchlist_entry() -> WatchlistEntry:
    return WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ")


def chart_now() -> datetime:
    return datetime(2026, 9, 23, 16, tzinfo=timezone.utc)


class RecordingMarketDataClient:
    def __init__(self, close: str = "200", bars: list[HistoricalBar] | None = None):
        self.calls: list[dict] = []
        self.close = Decimal(close)
        self.bars = bars

    def get_historical_bars(self, symbol, start, end, timeframe, adjustment):
        self.calls.append(
            {"symbol": symbol, "start": start, "end": end, "timeframe": timeframe, "adjustment": adjustment}
        )
        return (
            self.bars
            if self.bars is not None
            else [historical_bar(datetime(2026, 9, 23, 15, 30, tzinfo=timezone.utc), self.close)]
        )


def historical_bar(starts_at: datetime, close: Decimal) -> HistoricalBar:
    return HistoricalBar(
        starts_at=starts_at,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10,
        trade_count=1,
        vwap=close,
    )


class FakeChartDataSource:
    def load_chart(self, _entry, _chart_range, _now) -> ChartSnapshot:
        bar = ChartBar(
            starts_at=datetime(2026, 9, 23, 15, 30, tzinfo=timezone.utc),
            open=Decimal("200"),
            high=Decimal("201"),
            low=Decimal("199"),
            close=Decimal("200"),
            volume=10,
            session="regular",
        )
        return ChartSnapshot([bar], [bar], datetime(2026, 9, 23, 15, 45, tzinfo=timezone.utc))


class FakeTrading212Client:
    def __init__(self, positions: list[dict]):
        self.positions = positions
        self.get_positions_calls = 0

    def get_positions(self) -> list[dict]:
        self.get_positions_calls += 1
        return self.positions
