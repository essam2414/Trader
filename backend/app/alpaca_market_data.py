"""Alpaca market-data adapter for the read-only dashboard watchlist."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

NEW_YORK = ZoneInfo("America/New_York")
DATA_BASE_URL = "https://data.alpaca.markets"
TRADING_BASE_URL = "https://paper-api.alpaca.markets"
TICKER_LOGO_BASE_URL = "https://api.eulerpool.com/api/1/logo/ticker"
CATALOG_TTL_SECONDS = 24 * 60 * 60
QUOTE_TTL_SECONDS = 60
FRESH_AFTER_SECONDS = 5 * 60


class AlpacaUnavailableError(Exception):
    """Raised when the market-data provider cannot produce a fresh result."""


@dataclass(frozen=True)
class AlpacaAsset:
    asset_id: str
    symbol: str
    name: str
    exchange: str


@dataclass(frozen=True)
class SparklinePoint:
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class TradingSession:
    opens_at: datetime
    closes_at: datetime


@dataclass(frozen=True)
class MarketQuote:
    price: Decimal | None
    previous_close: Decimal | None
    dollar_change: Decimal | None
    percent_change: Decimal | None
    sparkline: list[SparklinePoint]
    feed: str
    source_timestamp: datetime | None
    source_type: str | None
    freshness: str
    is_extended_hours: bool


class AlpacaMarketDataClient:
    """Hide Alpaca catalog, calendar, quote, adjustment and retry details."""

    def __init__(self, api_key: str, api_secret: str, feed: str = "iex") -> None:
        if feed not in {"iex", "sip", "delayed_sip"}:
            raise ValueError("alpaca_data_feed must be iex, sip, or delayed_sip")
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
        self.feed = feed
        self._catalog: list[AlpacaAsset] = []
        self._catalog_loaded_at = 0.0
        self._calendar: dict[date, TradingSession] = {}
        self._calendar_loaded_for: date | None = None
        self._last_quotes: dict[str, MarketQuote] = {}
        self._quote_cache_key: tuple[str, ...] = ()
        self._quote_cache_loaded_at = 0.0

    def _request(self, base_url: str, path: str, params: dict[str, str]) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.get(f"{base_url}{path}", headers=self._headers, params=params, timeout=10.0)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Transient Alpaca response", request=response.request, response=response
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2 * (2**attempt))
        raise AlpacaUnavailableError("Alpaca market data is temporarily unavailable") from last_error

    def _load_catalog(self, force: bool = False) -> list[AlpacaAsset]:
        if not force and self._catalog and time.monotonic() - self._catalog_loaded_at < CATALOG_TTL_SECONDS:
            return self._catalog
        payload = self._request(
            TRADING_BASE_URL, "/v2/assets", {"status": "active", "asset_class": "us_equity"}
        )
        self._catalog = [
            AlpacaAsset(asset["id"], asset["symbol"], asset["name"], asset["exchange"])
            for asset in payload
            if asset.get("status") == "active" and asset.get("class") == "us_equity"
        ]
        self._catalog_loaded_at = time.monotonic()
        return self._catalog

    def search_us_equities(self, query: str) -> list[AlpacaAsset]:
        needle = query.strip().upper()
        if len(needle) < 1:
            return []
        matches = [
            asset
            for asset in self._load_catalog()
            if needle in asset.symbol.upper() or needle in asset.name.upper()
        ]

        def relevance(asset: AlpacaAsset) -> tuple[int, str, str]:
            symbol = asset.symbol.upper()
            name = asset.name.upper()
            if symbol == needle:
                return (0, symbol, name)
            if symbol.startswith(needle):
                return (1, symbol, name)
            if needle in symbol:
                return (2, symbol, name)
            if name.startswith(needle):
                return (3, symbol, name)
            return (4, symbol, name)

        return sorted(matches, key=relevance)[:10]

    def get_asset(self, asset_id: str) -> AlpacaAsset | None:
        for asset in self._load_catalog(force=True):
            if asset.asset_id == asset_id:
                return asset
        return None

    def get_company_logo(self, symbol: str) -> tuple[bytes, str] | None:
        """Fetch a company logo from the configured no-key ticker-logo provider."""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.get(
                    f"{TICKER_LOGO_BASE_URL}/{quote(symbol, safe='')}",
                    headers={"Accept": "image/*"},
                    timeout=10.0,
                )
                if response.status_code == 404:
                    return None
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Transient Alpaca response", request=response.request, response=response
                    )
                if response.status_code >= 400:
                    return None
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
                if not content_type.startswith("image/") or not response.content:
                    return None
                return response.content, content_type
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2 * (2**attempt))
        raise AlpacaUnavailableError("Company logos are temporarily unavailable") from last_error

    def _load_calendar(self, around: date) -> dict[date, TradingSession]:
        if self._calendar_loaded_for == around:
            return self._calendar
        start = around - timedelta(days=14)
        end = around + timedelta(days=1)
        payload = self._request(
            TRADING_BASE_URL,
            "/v2/calendar",
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        self._calendar = {}
        for session in payload:
            session_date = date.fromisoformat(session["date"])
            self._calendar[session_date] = TradingSession(
                opens_at=datetime.fromisoformat(f"{session['date']}T{session['open']}:00").replace(
                    tzinfo=NEW_YORK
                ),
                closes_at=datetime.fromisoformat(f"{session['date']}T{session['close']}:00").replace(
                    tzinfo=NEW_YORK
                ),
            )
        self._calendar_loaded_for = around
        return self._calendar

    def _sessions_for_price(self, source_timestamp: datetime) -> tuple[date, date, bool]:
        timestamp = source_timestamp.astimezone(NEW_YORK)
        calendar = self._load_calendar(timestamp.date())
        completed = [
            session_date for session_date, session in calendar.items() if session.closes_at <= timestamp
        ]
        if not completed:
            raise AlpacaUnavailableError("No completed regular session is available for this price")
        previous_close_session = max(completed)
        active_sessions = [
            session_date
            for session_date, session in calendar.items()
            if session.opens_at <= timestamp <= session.closes_at
        ]
        if active_sessions:
            return previous_close_session, max(active_sessions), False
        return previous_close_session, previous_close_session, True

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))

    def _daily_closes(self, symbols: list[str], session_date: date) -> dict[str, Decimal]:
        payload = self._request(
            DATA_BASE_URL,
            "/v2/stocks/bars",
            {
                "symbols": ",".join(symbols),
                "timeframe": "1Day",
                "start": session_date.isoformat(),
                "end": (session_date + timedelta(days=1)).isoformat(),
                "adjustment": "split",
                "feed": self.feed,
            },
        )
        return {
            symbol: self._decimal(bars[-1]["c"]) for symbol, bars in payload.get("bars", {}).items() if bars
        }

    def _intraday_bars(self, symbols: list[str], session_date: date) -> dict[str, list[SparklinePoint]]:
        session = self._load_calendar(session_date).get(session_date)
        if session is None:
            return {}
        payload = self._request(
            DATA_BASE_URL,
            "/v2/stocks/bars",
            {
                "symbols": ",".join(symbols),
                "timeframe": "5Min",
                "start": session.opens_at.astimezone(timezone.utc).isoformat(),
                "end": session.closes_at.astimezone(timezone.utc).isoformat(),
                "adjustment": "split",
                "feed": self.feed,
            },
        )
        result: dict[str, list[SparklinePoint]] = {}
        for symbol, bars in payload.get("bars", {}).items():
            points: list[SparklinePoint] = []
            for bar in bars:
                timestamp = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
                if session.opens_at <= timestamp.astimezone(NEW_YORK) < session.closes_at:
                    points.append(SparklinePoint(timestamp, self._decimal(bar["c"])))
            result[symbol] = points
        return result

    def get_watchlist_market_data(self, symbols: list[str]) -> dict[str, MarketQuote]:
        if not symbols:
            return {}
        cache_key = tuple(sorted(symbols))
        if (
            cache_key == self._quote_cache_key
            and time.monotonic() - self._quote_cache_loaded_at < QUOTE_TTL_SECONDS
        ):
            return {
                symbol: self._with_current_freshness(self._last_quotes[symbol])
                for symbol in symbols
                if symbol in self._last_quotes
            }
        try:
            snapshots = self._request(
                DATA_BASE_URL, "/v2/stocks/snapshots", {"symbols": ",".join(symbols), "feed": self.feed}
            )
            candidates: dict[str, tuple[Decimal, datetime, str]] = {}
            for symbol, snapshot in snapshots.items():
                trade = snapshot.get("latestTrade")
                if trade:
                    candidates[symbol] = (
                        self._decimal(trade["p"]),
                        datetime.fromisoformat(trade["t"].replace("Z", "+00:00")),
                        "latest_trade",
                    )
                elif snapshot.get("dailyBar"):
                    bar = snapshot["dailyBar"]
                    bar_date = (
                        datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(NEW_YORK).date()
                    )
                    session = self._load_calendar(bar_date).get(bar_date)
                    if session is None:
                        continue
                    candidates[symbol] = (
                        self._decimal(bar["c"]),
                        session.closes_at,
                        "daily_bar",
                    )
            close_groups: dict[date, list[str]] = {}
            sparkline_sessions: dict[str, date] = {}
            extended: dict[str, bool] = {}
            for symbol, (_, timestamp, _) in candidates.items():
                close_session, sparkline_session, is_extended = self._sessions_for_price(timestamp)
                close_groups.setdefault(close_session, []).append(symbol)
                sparkline_sessions[symbol] = sparkline_session
                extended[symbol] = is_extended
            closes = {session: self._daily_closes(group, session) for session, group in close_groups.items()}
            sparkline_groups: dict[date, list[str]] = {}
            for symbol, session in sparkline_sessions.items():
                sparkline_groups.setdefault(session, []).append(symbol)
            intraday = {
                session: self._intraday_bars(group, session) for session, group in sparkline_groups.items()
            }
            now = datetime.now(timezone.utc)
            quotes: dict[str, MarketQuote] = {}
            for session, group in close_groups.items():
                for symbol in group:
                    price, timestamp, source_type = candidates[symbol]
                    previous_close = closes[session].get(symbol)
                    dollar_change = price - previous_close if previous_close is not None else None
                    percent_change = (
                        (dollar_change / previous_close) * Decimal("100")
                        if dollar_change is not None and previous_close != 0
                        else None
                    )
                    quotes[symbol] = MarketQuote(
                        price=price,
                        previous_close=previous_close,
                        dollar_change=dollar_change,
                        percent_change=percent_change,
                        sparkline=intraday[sparkline_sessions[symbol]].get(symbol, []),
                        feed=self.feed,
                        source_timestamp=timestamp,
                        source_type=source_type,
                        freshness=(
                            "fresh" if now - timestamp <= timedelta(seconds=FRESH_AFTER_SECONDS) else "stale"
                        ),
                        is_extended_hours=extended[symbol],
                    )
            self._last_quotes.update(quotes)
            self._quote_cache_key = cache_key
            self._quote_cache_loaded_at = time.monotonic()
            return {symbol: quotes.get(symbol) or self._last_quotes.get(symbol) for symbol in symbols}
        except AlpacaUnavailableError:
            return {
                symbol: self._stale_copy(self._last_quotes[symbol])
                for symbol in symbols
                if symbol in self._last_quotes
            }

    @staticmethod
    def _stale_copy(quote: MarketQuote) -> MarketQuote:
        return MarketQuote(
            price=quote.price,
            previous_close=quote.previous_close,
            dollar_change=quote.dollar_change,
            percent_change=quote.percent_change,
            sparkline=quote.sparkline,
            feed=quote.feed,
            source_timestamp=quote.source_timestamp,
            source_type=quote.source_type,
            freshness="stale",
            is_extended_hours=quote.is_extended_hours,
        )

    @staticmethod
    def _with_current_freshness(quote: MarketQuote) -> MarketQuote:
        if quote.source_timestamp is None or quote.freshness == "unavailable":
            return quote
        freshness = (
            "fresh"
            if datetime.now(timezone.utc) - quote.source_timestamp <= timedelta(seconds=FRESH_AFTER_SECONDS)
            else "stale"
        )
        return MarketQuote(
            price=quote.price,
            previous_close=quote.previous_close,
            dollar_change=quote.dollar_change,
            percent_change=quote.percent_change,
            sparkline=quote.sparkline,
            feed=quote.feed,
            source_timestamp=quote.source_timestamp,
            source_type=quote.source_type,
            freshness=freshness,
            is_extended_hours=quote.is_extended_hours,
        )
