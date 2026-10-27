"""Calendar-aware SIP inputs, durable snapshots and bounded background refreshes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from threading import Lock

from sqlalchemy.orm import Session, sessionmaker

from app.alpaca_market_data import (
    NEW_YORK,
    AlpacaMarketDataClient,
    AlpacaUnavailableError,
    HistoricalBar,
    TradingSession,
)
from app.models import StockAnalysisSnapshot, WatchlistEntry
from app.schemas import StockAnalysisOut

from .stock_analysis import build_metrics, cumulative_rvol, valid_bar

logger = logging.getLogger(__name__)
DELAY = timedelta(minutes=15)
BAR = timedelta(minutes=5)
CALCULATION_VERSION = 2


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AnalysisWindow:
    daily_date: date
    context_date: date
    context_through: datetime
    daily_cycle: tuple[date, date]
    next_refresh: datetime


def analysis_window(calendar: dict[date, TradingSession], now: datetime) -> AnalysisWindow:
    """Use actual closes plus publication allowance, not weekdays or a fixed 16:00 close."""
    now = utc(now)
    completed = [
        day for day, session in sorted(calendar.items()) if session.closes_at + timedelta(minutes=20) <= now
    ]
    cutoff = now - DELAY
    cutoff = cutoff.replace(minute=(cutoff.minute // 5) * 5, second=0, microsecond=0)
    contexts = [day for day, session in sorted(calendar.items()) if session.opens_at + BAR <= cutoff]
    if not completed or not contexts:
        raise AlpacaUnavailableError("Exchange session history is unavailable")
    context_date = contexts[-1]
    through = min(cutoff, calendar[context_date].closes_at)
    mornings = [datetime.combine(day, time(8, 30), NEW_YORK) for day in sorted(calendar)]
    past_mornings = [moment.date() for moment in mornings if moment <= now]
    future = [moment for moment in mornings if moment > now]
    for session in calendar.values():
        close_ready = session.closes_at + timedelta(minutes=20)
        open_ready = session.opens_at + timedelta(minutes=20)
        future.extend(moment for moment in (close_ready, open_ready) if moment > now)
        if session.opens_at <= now < close_ready:
            future.append(now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0) + BAR)
    return AnalysisWindow(
        completed[-1],
        context_date,
        utc(through),
        (completed[-1], past_mornings[-1] if past_mornings else completed[-1]),
        utc(min(future)) if future else now + BAR,
    )


def daily_history(
    bars: list[HistoricalBar],
    calendar: dict[date, TradingSession],
    last_date: date,
) -> list[HistoricalBar]:
    """Use a contiguous suffix of actual sessions; never bridge gaps or count calendar days."""
    by_date = {bar.starts_at.astimezone(NEW_YORK).date(): bar for bar in bars if valid_bar(bar)}
    if last_date not in by_date:
        raise AlpacaUnavailableError("The latest completed session is missing")
    suffix = []
    for day in reversed(sorted(day for day in calendar if day <= last_date)):
        if day not in by_date or len(suffix) == 250:
            break
        suffix.append(by_date[day])
    return list(reversed(suffix))


def read_snapshot(db: Session, entry: WatchlistEntry, now: datetime) -> StockAnalysisOut:
    row = db.get(StockAnalysisSnapshot, entry.alpaca_asset_id)
    if row is None or not row.payload:
        return StockAnalysisOut(
            assetId=entry.alpaca_asset_id,
            symbol=entry.symbol,
            status="unavailable" if row and row.last_error else "loading",
            message=row.last_error if row else "Preparing stock analysis…",
            nextRefreshAt=utc(row.next_refresh_at) if row else None,
        )
    if row.payload.get("_calculation_version") != CALCULATION_VERSION:
        return StockAnalysisOut(
            assetId=entry.alpaca_asset_id,
            symbol=entry.symbol,
            status="unavailable" if row.last_error else "loading",
            message=row.last_error or "Refreshing analysis with updated calculations…",
            nextRefreshAt=utc(row.next_refresh_at) if row.last_error else now,
        )
    result = StockAnalysisOut.model_validate(row.payload)
    # Results for an old symbol must not be presented as fresh after a rename.
    if row.last_error or now >= utc(row.next_refresh_at) or result.symbol != entry.symbol:
        result.status = "stale"
        result.message = row.last_error or "Showing the last calculation while updated data is prepared."
    result.nextRefreshAt = utc(row.next_refresh_at)
    return result


class StockAnalysisService:
    """One interface for refreshing watchlist analysis; calculations require no provider access."""

    def __init__(self, client: AlpacaMarketDataClient, sessions: sessionmaker) -> None:
        if client.feed != "sip":
            raise ValueError("Analysis requires consistently consolidated SIP data")
        self._client = client
        self._sessions = sessions
        self._lock = Lock()
        self._calendar_date: date | None = None
        self._calendar: dict[date, TradingSession] = {}
        self._daily: dict[str, tuple[tuple[date, date], list[HistoricalBar]]] = {}
        self._intraday: dict[str, tuple[tuple[date, date], datetime, list[HistoricalBar]]] = {}

    def refresh_watchlist(self) -> None:
        with self._sessions() as db:
            entries = db.query(WatchlistEntry).all()
            ids = [entry.alpaca_asset_id for entry in entries]
            symbols = {entry.symbol for entry in entries} | {"SPY"}
        for asset_id in ids:
            self.refresh_asset(asset_id)
        if self._lock.acquire(blocking=False):
            try:
                self._daily = {key: value for key, value in self._daily.items() if key in symbols}
                self._intraday = {key: value for key, value in self._intraday.items() if key in symbols}
            finally:
                self._lock.release()

    def refresh_asset(self, asset_id: str, now: datetime | None = None) -> None:
        # Serialize provider calls and avoid duplicate work from scheduled and browser refreshes.
        if not self._lock.acquire(blocking=False):
            return
        try:
            with self._sessions() as db:
                entry = db.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
                if entry is None:
                    return
                as_of = utc(now or datetime.now(timezone.utc))
                row = db.get(StockAnalysisSnapshot, asset_id)
                if (
                    row
                    and utc(row.next_refresh_at) > as_of
                    and row.payload.get("symbol", entry.symbol) == entry.symbol
                    and (row.last_error or row.payload.get("_calculation_version") == CALCULATION_VERSION)
                ):
                    return
                if row is None:
                    row = StockAnalysisSnapshot(alpaca_asset_id=asset_id, payload={}, next_refresh_at=as_of)
                    db.add(row)
                try:
                    result, next_refresh = self._calculate(entry, as_of)
                    row.payload = {
                        **result.model_dump(mode="json"),
                        "_calculation_version": CALCULATION_VERSION,
                    }
                    row.last_error = None
                    row.next_refresh_at = next_refresh
                except (AlpacaUnavailableError, ValueError, KeyError, TypeError, ArithmeticError):
                    # Do not expose provider messages or credential-bearing URLs.
                    row.last_error = "Market data is temporarily unavailable or incomplete. Retrying shortly."
                    row.next_refresh_at = as_of + BAR
                db.commit()
        except Exception:
            # A single failed stock must not stop the remaining watchlist refresh.
            logger.warning("Stock analysis refresh failed for asset %s", asset_id)
        finally:
            self._lock.release()

    def _load_calendar(self, now: datetime) -> dict[date, TradingSession]:
        local_date = now.astimezone(NEW_YORK).date()
        if self._calendar_date != local_date:
            calendar = self._client.get_calendar_sessions(
                local_date - timedelta(days=550), local_date + timedelta(days=14)
            )
            if not calendar:
                raise AlpacaUnavailableError("Exchange calendar is empty")
            self._calendar, self._calendar_date = calendar, local_date
        return self._calendar

    def _daily_bars(
        self, symbol: str, calendar: dict[date, TradingSession], window: AnalysisWindow, now: datetime
    ) -> list[HistoricalBar]:
        cached = self._daily.get(symbol)
        if cached and cached[0] == window.daily_cycle:
            return cached[1]
        dates = sorted(day for day in calendar if day <= window.daily_date)[-250:]
        start = datetime.combine(dates[0], time.min, NEW_YORK)
        end = min(
            now - DELAY,
            datetime.combine(window.daily_date + timedelta(days=1), time.min, NEW_YORK)
            - timedelta(microseconds=1),
        )
        bars = self._client.get_historical_bars(symbol, start, end, "1Day", adjustment="split")
        result = daily_history(bars, calendar, window.daily_date)
        self._daily[symbol] = (window.daily_cycle, result)
        return result

    def _intraday_bars(
        self, symbol: str, calendar: dict[date, TradingSession], window: AnalysisWindow
    ) -> list[HistoricalBar]:
        cached = self._intraday.get(symbol)
        dates = sorted(day for day in calendar if day <= window.context_date)[-35:]
        earliest = calendar[dates[0]].opens_at
        existing: list[HistoricalBar] = []
        start = earliest
        if cached and cached[0] == window.daily_cycle:
            if cached[1] == window.context_through:
                return cached[2]
            existing = cached[2]
            start = max(earliest, cached[1] - timedelta(minutes=15))
        incoming = self._client.get_historical_bars(
            symbol, start, window.context_through - timedelta(microseconds=1), "5Min", adjustment="split"
        )
        # Replace the overlapping correction window, including removed provider bars.
        by_time = {bar.starts_at: bar for bar in existing if earliest <= bar.starts_at < start}
        by_time.update(
            {
                bar.starts_at: bar
                for bar in incoming
                if earliest <= bar.starts_at and bar.starts_at + BAR <= window.context_through
            }
        )
        result = sorted(by_time.values(), key=lambda bar: bar.starts_at)
        self._intraday[symbol] = (window.daily_cycle, window.context_through, result)
        return result

    def _calculate(self, entry: WatchlistEntry, now: datetime) -> tuple[StockAnalysisOut, datetime]:
        calendar = self._load_calendar(now)
        window = analysis_window(calendar, now)
        daily = self._daily_bars(entry.symbol, calendar, window, now)
        messages: list[str] = []
        try:
            benchmark = self._daily_bars("SPY", calendar, window, now)
        except AlpacaUnavailableError:
            benchmark = []
            messages.append("Market comparison is temporarily unavailable.")
        session = calendar[window.context_date]
        # The last 5-minute bar ends before the closing auction. Once the daily
        # candle is settled, use its close consistently with the daily indicators.
        settled = window.context_date == window.daily_date and window.context_through == utc(
            session.closes_at
        )
        price = daily[-1].close if settled else None
        intraday_as_of = window.context_through if settled else None
        rvol = None
        try:
            intraday = self._intraday_bars(entry.symbol, calendar, window)
            current = [
                bar
                for bar in intraday
                if session.opens_at <= bar.starts_at
                and bar.starts_at + BAR <= window.context_through
                and valid_bar(bar)
            ]
            if current and current[-1].starts_at + BAR == window.context_through:
                if not settled:
                    price = current[-1].close
                intraday_as_of = window.context_through
                rvol = cumulative_rvol(intraday, calendar, window.context_date, window.context_through)
            else:
                messages.append("Recent regular-session price or volume is incomplete.")
        except AlpacaUnavailableError:
            messages.append("Intraday price and volume are temporarily unavailable.")
        if rvol is None:
            # A partial response must be retried even when the market is closed
            # and the requested cutoff no longer advances.
            self._intraday.pop(entry.symbol, None)
        rows = build_metrics(daily, benchmark, price, window.context_date, rvol)
        if len(daily) < 250:
            messages.append(
                f"Using {len(daily)} consecutive completed sessions (250 preferred for smoothing)."
            )
        partial = bool(messages) or any(row.value is None for row in rows)
        # Retry missing coverage soon instead of freezing partial results all weekend.
        next_refresh = min(window.next_refresh, now + BAR) if partial else window.next_refresh
        result = StockAnalysisOut(
            assetId=entry.alpaca_asset_id,
            symbol=entry.symbol,
            status="partial" if partial else "ready",
            dailyAsOf=utc(calendar[window.daily_date].closes_at),
            intradayAsOf=intraday_as_of,
            calculatedAt=now,
            nextRefreshAt=next_refresh,
            historySessions=len(daily),
            message=" ".join(messages) or None,
            metrics=rows,
        )
        return result, next_refresh
