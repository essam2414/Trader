"""Calendar timing, cache reuse, persistence and provider isolation."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.alpaca_market_data import NEW_YORK, AlpacaUnavailableError, HistoricalBar, TradingSession
from app.config import settings
from app.dependencies import get_stock_analysis
from app.main import app
from app.models import StockAnalysisSnapshot, WatchlistEntry
from app.services.stock_analysis import daily_indicators
from app.services.stock_analysis_data import (
    StockAnalysisService,
    analysis_window,
    daily_history,
    read_snapshot,
)


def calendar_days():
    result = {}
    day = date(2025, 7, 1)
    while day <= date(2026, 10, 15):
        if day.weekday() < 5:
            result[day] = TradingSession(
                datetime.combine(day, time(9, 30), NEW_YORK), datetime.combine(day, time(16), NEW_YORK)
            )
        day += timedelta(days=1)
    return result


class FakeData:
    feed = "sip"

    def __init__(self):
        self.calendar = calendar_days()
        self.calls = []
        self.fail = False
        self.calendar_calls = 0
        self.daily_limit = None

    def get_calendar_sessions(self, start, end):
        self.calendar_calls += 1
        if self.fail:
            raise AlpacaUnavailableError("secret URL must not leak")
        return {day: session for day, session in self.calendar.items() if start <= day <= end}

    def get_historical_bars(self, symbol, start, end, timeframe, adjustment):
        self.calls.append((symbol, timeframe, adjustment, start, end))
        if self.fail:
            raise AlpacaUnavailableError("secret URL must not leak")
        bars = []
        for index, (day, session) in enumerate(sorted(self.calendar.items())):
            price = Decimal(100) + Decimal(index) / 10
            timestamps = (
                [datetime.combine(day, time.min, NEW_YORK)]
                if timeframe == "1Day"
                else [
                    session.opens_at + timedelta(minutes=5 * offset)
                    for offset in range(int((session.closes_at - session.opens_at).total_seconds()) // 300)
                ]
            )
            for timestamp in timestamps:
                if start <= timestamp <= end:
                    bars.append(HistoricalBar(timestamp, price, price + 1, price - 1, price, 100, None, None))
        return bars[-self.daily_limit :] if timeframe == "1Day" and self.daily_limit else bars


def entry(db, asset_id="asset-sndk", symbol="SNDK"):
    row = WatchlistEntry(alpaca_asset_id=asset_id, symbol=symbol, name=symbol, exchange="NASDAQ")
    db.add(row)
    db.commit()
    return row


def test_calendar_waits_for_actual_close_plus_twenty_minutes_and_handles_holiday():
    calendar = calendar_days()
    early = date(2026, 10, 2)
    session = calendar[early]
    calendar[early] = TradingSession(session.opens_at, datetime(2026, 10, 2, 13, tzinfo=NEW_YORK))
    before = analysis_window(calendar, datetime(2026, 10, 2, 13, 19, tzinfo=NEW_YORK))
    after = analysis_window(calendar, datetime(2026, 10, 2, 13, 20, tzinfo=NEW_YORK))
    assert before.daily_date == date(2026, 10, 1)
    assert after.daily_date == early
    assert after.context_through == session.opens_at.replace(hour=13, minute=0)
    assert before.next_refresh == after.context_through + timedelta(minutes=20)
    del calendar[date(2026, 10, 5)]
    holiday = analysis_window(calendar, datetime(2026, 10, 5, 12, tzinfo=NEW_YORK))
    assert holiday.daily_date == holiday.context_date == early
    assert holiday.next_refresh == datetime(2026, 10, 6, 8, 30, tzinfo=NEW_YORK)


def test_daylight_saving_calendar_preserves_session_close():
    calendar = {
        date(2026, 3, 6): TradingSession(
            datetime(2026, 3, 6, 9, 30, tzinfo=NEW_YORK), datetime(2026, 3, 6, 16, tzinfo=NEW_YORK)
        ),
        date(2026, 3, 9): TradingSession(
            datetime(2026, 3, 9, 9, 30, tzinfo=NEW_YORK), datetime(2026, 3, 9, 16, tzinfo=NEW_YORK)
        ),
    }
    window = analysis_window(calendar, datetime(2026, 3, 9, 20, 20, tzinfo=timezone.utc))
    assert window.daily_date == date(2026, 3, 9)
    assert window.context_through == datetime(2026, 3, 9, 20, tzinfo=timezone.utc)


def test_refresh_reuses_shared_benchmark_and_daily_history_but_advances_intraday(db_session):
    first = entry(db_session)
    entry(db_session, "asset-msft", "MSFT")
    provider = FakeData()
    service = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    now = datetime(2026, 10, 5, 11, 45, tzinfo=NEW_YORK)
    service.refresh_asset(first.alpaca_asset_id, now)
    service.refresh_asset("asset-msft", now)
    snapshot = read_snapshot(db_session, first, now)
    assert snapshot.status == "ready"
    assert snapshot.historySessions == 250
    assert snapshot.dailyAsOf == datetime(2026, 10, 2, 16, tzinfo=NEW_YORK)
    assert snapshot.intradayAsOf == datetime(2026, 10, 5, 11, 30, tzinfo=NEW_YORK)
    assert provider.calendar_calls == 1
    assert len([call for call in provider.calls if call[:2] == ("SPY", "1Day")]) == 1
    assert all(call[2] == "split" for call in provider.calls)
    count = len(provider.calls)
    service.refresh_asset(first.alpaca_asset_id, now + timedelta(minutes=1))
    assert len(provider.calls) == count
    service.refresh_asset(first.alpaca_asset_id, now + timedelta(minutes=5))
    assert len(provider.calls) == count + 1
    assert provider.calls[-1][1] == "5Min"
    assert provider.calls[-1][3] >= now - timedelta(minutes=30)
    assert provider.calls[-1][4] < now + timedelta(minutes=5) - timedelta(minutes=15)


def test_preopen_and_after_close_recheck_adjusted_history(db_session):
    item = entry(db_session)
    provider = FakeData()
    service = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    for now in [
        datetime(2026, 10, 5, 8, 25, tzinfo=NEW_YORK),
        datetime(2026, 10, 5, 8, 30, tzinfo=NEW_YORK),
        datetime(2026, 10, 5, 16, 20, tzinfo=NEW_YORK),
    ]:
        service.refresh_asset(item.alpaca_asset_id, now)
    assert len([call for call in provider.calls if call[:2] == ("SNDK", "1Day")]) == 3


def test_shorter_warmup_history_does_not_claim_available_metrics_are_missing(db_session):
    item = entry(db_session)
    provider = FakeData()
    provider.daily_limit = 166
    service = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    now = datetime(2026, 10, 5, 11, 45, tzinfo=NEW_YORK)
    service.refresh_asset(item.alpaca_asset_id, now)
    result = read_snapshot(db_session, item, now)
    assert result.status == "partial"
    assert result.historySessions == 166
    assert all(metric.value is not None for metric in result.metrics)
    assert "250 preferred for smoothing" in result.message


def test_failed_refresh_keeps_durable_snapshot_and_does_not_expose_provider_error(db_session):
    item = entry(db_session)
    provider = FakeData()
    service = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    now = datetime(2026, 10, 5, 11, 45, tzinfo=NEW_YORK)
    service.refresh_asset(item.alpaca_asset_id, now)
    original = read_snapshot(db_session, item, now)
    provider.fail = True
    later = datetime(2026, 10, 6, 11, 45, tzinfo=NEW_YORK)
    service.refresh_asset(item.alpaca_asset_id, later)
    db_session.expire_all()
    stale = read_snapshot(db_session, item, later)
    assert stale.status == "stale"
    assert stale.calculatedAt == original.calculatedAt
    assert stale.metrics == original.metrics
    assert "secret" not in stale.model_dump_json()
    assert stale.nextRefreshAt == later + timedelta(minutes=5)
    # A restarted module reads the same saved result without an in-memory history cache.
    restarted = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    restarted.refresh_asset(item.alpaca_asset_id, later + timedelta(seconds=1))
    assert read_snapshot(db_session, item, later).calculatedAt == original.calculatedAt


def test_missing_interior_session_limits_history_and_missing_latest_is_unavailable():
    provider = FakeData()
    end = datetime(2026, 10, 2, 18, tzinfo=NEW_YORK)
    bars = provider.get_historical_bars("SNDK", datetime(2026, 9, 1, tzinfo=NEW_YORK), end, "1Day", "split")
    del bars[-3]
    assert len(daily_history(bars, provider.calendar, date(2026, 10, 2))) == 2
    with pytest.raises(AlpacaUnavailableError):
        daily_history(bars[:-1], provider.calendar, date(2026, 10, 2))


def test_snapshot_endpoint_auth_missing_stock_and_background_loading(client, db_session):
    item = entry(db_session)
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}
    assert client.get(f"/api/watchlist/{item.alpaca_asset_id}/analysis").status_code == 401
    assert client.get("/api/watchlist/unknown/analysis", headers=headers).status_code == 404
    response = client.get(f"/api/watchlist/{item.alpaca_asset_id}/analysis", headers=headers)
    assert response.json()["status"] == "unavailable"
    calls = []

    class RecordingAnalysis:
        def refresh_asset(self, asset_id):
            calls.append(asset_id)

    app.dependency_overrides[get_stock_analysis] = lambda: RecordingAnalysis()
    response = client.get(f"/api/watchlist/{item.alpaca_asset_id}/analysis", headers=headers)
    assert response.json()["status"] == "loading"
    assert calls == [item.alpaca_asset_id]
    assert db_session.query(StockAnalysisSnapshot).count() == 0


def test_after_close_price_context_uses_settled_daily_close_not_last_intraday_trade(db_session):
    class ClosingAuctionData(FakeData):
        def get_historical_bars(self, *args, **kwargs):
            bars = super().get_historical_bars(*args, **kwargs)
            if self.calls[-1][1] == "5Min":
                bars[-1] = replace(bars[-1], close=bars[-1].close + 1)
            return bars

    item = entry(db_session)
    provider = ClosingAuctionData()
    service = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    now = datetime(2026, 10, 2, 16, 25, tzinfo=NEW_YORK)
    service.refresh_asset(item.alpaca_asset_id, now)
    daily = service._daily[item.symbol][1]
    values = daily_indicators(daily)
    expected = (daily[-1].close - values.ema20[-1]) / values.atr[-1]
    actual = next(
        metric for metric in read_snapshot(db_session, item, now).metrics if metric.id == "extension"
    )
    assert actual.value == pytest.approx(float(expected))


def test_outdated_calculation_snapshot_is_rebuilt_even_before_its_refresh_deadline(db_session):
    item = entry(db_session)
    service = StockAnalysisService(FakeData(), sessionmaker(bind=db_session.get_bind()))
    now = datetime(2026, 10, 2, 16, 25, tzinfo=NEW_YORK)
    service.refresh_asset(item.alpaca_asset_id, now)
    row = db_session.get(StockAnalysisSnapshot, item.alpaca_asset_id)
    row.payload = {key: value for key, value in row.payload.items() if key != "_calculation_version"}
    db_session.commit()
    obsolete = read_snapshot(db_session, item, now + timedelta(seconds=1))
    assert obsolete.status == "loading"
    assert obsolete.metrics == []
    assert obsolete.nextRefreshAt <= now + timedelta(seconds=1)
    service.refresh_asset(item.alpaca_asset_id, now + timedelta(seconds=1))
    db_session.expire_all()
    refreshed = read_snapshot(db_session, item, now + timedelta(seconds=1))
    assert refreshed.status == "ready"
    assert refreshed.calculatedAt == now + timedelta(seconds=1)


def test_missing_volume_is_refetched_when_market_closed_and_cutoff_is_unchanged(db_session):
    class CorrectedVolumeData(FakeData):
        missing = True

        def get_historical_bars(self, *args, **kwargs):
            bars = super().get_historical_bars(*args, **kwargs)
            if self.calls[-1][1] == "5Min" and self.missing:
                del bars[-2]
            return bars

    item = entry(db_session)
    provider = CorrectedVolumeData()
    service = StockAnalysisService(provider, sessionmaker(bind=db_session.get_bind()))
    now = datetime(2026, 10, 2, 16, 25, tzinfo=NEW_YORK)
    service.refresh_asset(item.alpaca_asset_id, now)
    original = read_snapshot(db_session, item, now)
    assert original.status == "partial"
    provider.missing = False
    service.refresh_asset(item.alpaca_asset_id, now + timedelta(minutes=5))
    db_session.expire_all()
    refreshed = read_snapshot(db_session, item, now + timedelta(minutes=5))
    assert refreshed.status == "ready"
    assert next(metric for metric in refreshed.metrics if metric.id == "rvol20").value == 1
