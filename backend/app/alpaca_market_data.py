"""Alpaca market-data adapter for the read-only dashboard watchlist."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as clock_time
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

NEW_YORK = ZoneInfo("America/New_York")
DATA_BASE_URL = "https://data.alpaca.markets"
TRADING_BASE_URL = "https://paper-api.alpaca.markets"
TICKER_LOGO_BASE_URL = "https://api.loadlogo.com/ticker"
DOMAIN_LOGO_BASE_URL = "https://img.loadlogo.com"
CATALOG_TTL_SECONDS = 24 * 60 * 60
QUOTE_TTL_SECONDS = 60
FRESH_AFTER_SECONDS = 5 * 60
PRE_MARKET_OPEN = clock_time(4, 0)
REGULAR_MARKET_CLOSE = clock_time(16, 0)
AFTER_HOURS_CLOSE = clock_time(20, 0)
SPARKLINE_WINDOW = timedelta(hours=24)
SPARKLINE_TIMEFRAME = "15Min"
SPARKLINE_REQUEST_LIMIT = 10_000


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
class HistoricalBar:
    """Raw OHLCV data from one provider aggregation interval."""

    starts_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    trade_count: int | None
    vwap: Decimal | None


@dataclass(frozen=True)
class TradingSession:
    opens_at: datetime
    closes_at: datetime


@dataclass(frozen=True)
class MarketSessionStatus:
    """The current US equity trading phase and its next scheduled transition."""

    phase: str
    as_of: datetime
    ends_at: datetime | None
    next_phase: str | None
    next_phase_starts_at: datetime | None
    is_early_close: bool


@dataclass(frozen=True)
class _ScheduledMarketPhase:
    phase: str
    starts_at: datetime
    ends_at: datetime
    is_early_close: bool = False


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


@dataclass(frozen=True)
class NewsArticle:
    """One Alpaca news article, retaining the full provider record for its detail view."""

    article_id: int
    headline: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
    symbols: list[str]
    raw_data: dict[str, Any]


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
        """Resolve a ticker to its domain, then fetch its image from LoadLogo."""
        metadata = self._logo_request(f"{TICKER_LOGO_BASE_URL}/{quote(symbol, safe='')}", "application/json")
        if metadata is None:
            return None
        try:
            domain = metadata.json().get("domain")
        except (ValueError, AttributeError):
            return None
        if not isinstance(domain, str) or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain.lower()
        ):
            return None
        image = self._logo_request(f"{DOMAIN_LOGO_BASE_URL}/{domain.lower()}", "image/*")
        if image is None:
            return None
        content_type = image.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
        if (
            content_type not in {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}
            or not image.content
        ):
            return None
        return image.content, content_type

    @staticmethod
    def _logo_request(url: str, accept: str) -> httpx.Response | None:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = httpx.get(url, headers={"Accept": accept}, timeout=3.0)
                if response.status_code in {404, 422}:
                    return None
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Transient logo provider response", request=response.request, response=response
                    )
                if response.status_code >= 400:
                    return None
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < 1:
                    time.sleep(0.2 * (2**attempt))
        raise AlpacaUnavailableError("Company logos are temporarily unavailable") from last_error

    def _load_calendar(self, around: date) -> dict[date, TradingSession]:
        if self._calendar_loaded_for == around:
            return self._calendar
        start = around - timedelta(days=14)
        end = around + timedelta(days=14)
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

    @staticmethod
    def _at_new_york_time(session_date: date, value: clock_time) -> datetime:
        return datetime.combine(session_date, value, tzinfo=NEW_YORK)

    def get_market_session(self, now: datetime | None = None) -> MarketSessionStatus:
        """Return the current US equity market phase from Alpaca's exchange calendar.

        The calendar is the source of truth for holidays and regular-session early closes.
        Overnight is only scheduled when its following regular trading date appears in that
        calendar, so it is suppressed before a market holiday.
        """
        as_of = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK)
        calendar = self._load_calendar(as_of.date())
        phases: list[_ScheduledMarketPhase] = []

        for session_date, session in calendar.items():
            overnight_start = self._at_new_york_time(session_date - timedelta(days=1), AFTER_HOURS_CLOSE)
            pre_market_start = self._at_new_york_time(session_date, PRE_MARKET_OPEN)
            is_early_close = session.closes_at.timetz().replace(tzinfo=None) < REGULAR_MARKET_CLOSE
            phases.extend(
                [
                    _ScheduledMarketPhase("overnight", overnight_start, pre_market_start),
                    _ScheduledMarketPhase("pre_market", pre_market_start, session.opens_at),
                    _ScheduledMarketPhase(
                        "regular", session.opens_at, session.closes_at, is_early_close=is_early_close
                    ),
                ]
            )
            if not is_early_close:
                after_hours_end = self._at_new_york_time(session_date, AFTER_HOURS_CLOSE)
                phases.append(_ScheduledMarketPhase("after_hours", session.closes_at, after_hours_end))

        phases.sort(key=lambda phase: phase.starts_at)
        active_phase = next((phase for phase in phases if phase.starts_at <= as_of < phase.ends_at), None)
        if active_phase is not None:
            next_phase = next((phase for phase in phases if phase.starts_at >= active_phase.ends_at), None)
            return MarketSessionStatus(
                phase=active_phase.phase,
                as_of=as_of,
                ends_at=active_phase.ends_at,
                next_phase=next_phase.phase if next_phase else None,
                next_phase_starts_at=next_phase.starts_at if next_phase else None,
                is_early_close=active_phase.is_early_close,
            )

        next_phase = next((phase for phase in phases if phase.starts_at > as_of), None)
        return MarketSessionStatus(
            phase="closed",
            as_of=as_of,
            ends_at=None,
            next_phase=next_phase.phase if next_phase else None,
            next_phase_starts_at=next_phase.starts_at if next_phase else None,
            is_early_close=False,
        )

    def _sessions_for_price(self, source_timestamp: datetime) -> tuple[date, date, bool]:
        """Return the prior trading close and trading session for a quoted price.

        The prior close is intentionally fixed for the whole trading day, including
        pre-market and after-hours.  Alpaca's calendar supplies the business-day
        boundaries, so weekends and market holidays cannot become baselines.
        """
        timestamp = source_timestamp.astimezone(NEW_YORK)
        calendar = self._load_calendar(timestamp.date())
        session_date = timestamp.date()
        session = calendar.get(session_date)
        if session is None:
            future_sessions = [date_value for date_value in calendar if date_value > session_date]
            current_session = min(future_sessions) if future_sessions else max(calendar)
        else:
            current_session = session_date

        prior_sessions = [date_value for date_value in calendar if date_value < current_session]
        if not prior_sessions:
            raise AlpacaUnavailableError("No completed regular session is available for this price")
        previous_close_session = max(prior_sessions)
        is_extended = session is None or not (session.opens_at <= timestamp <= session.closes_at)
        return previous_close_session, current_session, is_extended

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))

    def _daily_closes(self, symbols: list[str], session_date: date) -> dict[str, Decimal]:
        """Load the final Last Trade Price for one completed trading session."""
        session_start = datetime.combine(session_date, clock_time.min, tzinfo=timezone.utc)
        session_end = session_start + timedelta(days=1)
        payload = self._request(
            DATA_BASE_URL,
            "/v2/stocks/bars",
            {
                "symbols": ",".join(symbols),
                "timeframe": "1Day",
                # Alpaca treats date-only end values inclusively.  Explicit UTC
                # instants prevent today's still-forming daily bar being chosen
                # as the prior close.
                "start": session_start.isoformat(),
                "end": session_end.isoformat(),
                "adjustment": "raw",
                "feed": "sip",
            },
        )
        return {
            symbol: self._decimal(bars[-1]["c"]) for symbol, bars in payload.get("bars", {}).items() if bars
        }

    def get_historical_bars(
        self,
        symbol: str,
        start: datetime | None,
        end: datetime | None,
        timeframe: str,
        adjustment: str = "raw",
    ) -> list[HistoricalBar]:
        """Load every page of one symbol's raw history in chronological order."""
        params = {
            "symbols": symbol,
            "timeframe": timeframe,
            "adjustment": adjustment,
            "feed": self.feed,
            "limit": "10000",
            "sort": "asc",
        }
        if start is not None:
            params["start"] = start.astimezone(timezone.utc).isoformat()
        if end is not None:
            params["end"] = end.astimezone(timezone.utc).isoformat()
        result: list[HistoricalBar] = []
        page_token: str | None = None
        while True:
            request_params = {**params, **({"page_token": page_token} if page_token else {})}
            payload = self._request(DATA_BASE_URL, "/v2/stocks/bars", request_params)
            grouped = payload.get("bars", {})
            raw_bars = grouped.get(symbol, []) if isinstance(grouped, dict) else grouped
            for bar in raw_bars:
                result.append(
                    HistoricalBar(
                        starts_at=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                        open=self._decimal(bar["o"]),
                        high=self._decimal(bar["h"]),
                        low=self._decimal(bar["l"]),
                        close=self._decimal(bar["c"]),
                        volume=int(bar["v"]),
                        trade_count=int(bar["n"]) if bar.get("n") is not None else None,
                        vwap=self._decimal(bar["vw"]) if bar.get("vw") is not None else None,
                    )
                )
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return result

    def get_corporate_actions(self, symbol: str, start: date, end: date) -> dict[str, Any]:
        """Return the provider's complete corporate-action envelope for an asset."""
        params = {
            "symbols": symbol,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "data_quality": "complete",
            "limit": "1000",
            "sort": "asc",
        }
        result: dict[str, Any] = {}
        page_token: str | None = None
        while True:
            request_params = {**params, **({"page_token": page_token} if page_token else {})}
            payload = self._request(DATA_BASE_URL, "/v1/corporate-actions", request_params)
            for key, value in payload.items():
                if key == "next_page_token":
                    continue
                if isinstance(value, list):
                    result.setdefault(key, []).extend(value)
                else:
                    result[key] = value
            page_token = payload.get("next_page_token")
            if not page_token:
                return result

    @staticmethod
    def _sparkline_bucket(timestamp: datetime) -> datetime:
        """Round a price timestamp down to its containing 15-minute chart bar."""
        value = timestamp.astimezone(timezone.utc)
        return value.replace(minute=value.minute - value.minute % 15, second=0, microsecond=0)

    def _rolling_sparklines(self, symbols: list[str], as_of: datetime) -> dict[str, list[SparklinePoint]]:
        """Return chronological 15-minute prices across the preceding 24 clock hours."""
        if not symbols:
            return {}
        window_end = as_of.astimezone(timezone.utc)
        window_start = window_end - SPARKLINE_WINDOW
        payload = self._request(
            DATA_BASE_URL,
            "/v2/stocks/bars",
            {
                "symbols": ",".join(symbols),
                "timeframe": SPARKLINE_TIMEFRAME,
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
                "adjustment": "split",
                "feed": self.feed,
                "limit": str(SPARKLINE_REQUEST_LIMIT),
                "sort": "asc",
            },
        )
        result: dict[str, list[SparklinePoint]] = {}
        for symbol, bars in payload.get("bars", {}).items():
            points_by_timestamp: dict[datetime, SparklinePoint] = {}
            for bar in bars:
                timestamp = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
                if window_start <= timestamp <= window_end:
                    points_by_timestamp[timestamp] = SparklinePoint(timestamp, self._decimal(bar["c"]))
            result[symbol] = [points_by_timestamp[key] for key in sorted(points_by_timestamp)]
        return result

    def _with_current_sparkline_price(
        self,
        points: list[SparklinePoint],
        timestamp: datetime,
        price: Decimal,
        as_of: datetime,
    ) -> list[SparklinePoint]:
        """Overlay the current quote into its bar so a chart ends at the displayed price."""
        window_start = as_of.astimezone(timezone.utc) - SPARKLINE_WINDOW
        bucket = self._sparkline_bucket(timestamp)
        points_by_timestamp = {
            point.timestamp: point
            for point in points
            if window_start <= point.timestamp.astimezone(timezone.utc) <= as_of.astimezone(timezone.utc)
        }
        if window_start <= bucket <= as_of.astimezone(timezone.utc):
            points_by_timestamp[bucket] = SparklinePoint(bucket, price)
        return [points_by_timestamp[key] for key in sorted(points_by_timestamp)]

    def get_watchlist_market_data(
        self, symbols: list[str], now: datetime | None = None
    ) -> dict[str, MarketQuote]:
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
            extended: dict[str, bool] = {}
            for symbol, (_, timestamp, _) in candidates.items():
                close_session, _, is_extended = self._sessions_for_price(timestamp)
                close_groups.setdefault(close_session, []).append(symbol)
                extended[symbol] = is_extended
            closes = {session: self._daily_closes(group, session) for session, group in close_groups.items()}
            as_of = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            sparklines = self._rolling_sparklines(list(candidates), as_of)
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
                        sparkline=self._with_current_sparkline_price(
                            sparklines.get(symbol, []), timestamp, price, as_of
                        ),
                        feed=self.feed,
                        source_timestamp=timestamp,
                        source_type=source_type,
                        freshness=(
                            "fresh"
                            if as_of - timestamp <= timedelta(seconds=FRESH_AFTER_SECONDS)
                            else "stale"
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

    def get_watchlist_news(self, symbols: list[str], limit: int = 50) -> list[NewsArticle]:
        """Return the newest unique articles that Alpaca associates with a watchlist symbol."""
        watchlist_symbols = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        if not watchlist_symbols:
            return []
        payload = self._request(
            DATA_BASE_URL,
            "/v1beta1/news",
            {
                "symbols": ",".join(sorted(watchlist_symbols)),
                "limit": str(limit),
                "sort": "desc",
                "include_content": "true",
            },
        )
        by_id: dict[int, NewsArticle] = {}
        for article in payload.get("news", []):
            article_symbols = [str(symbol).upper() for symbol in article.get("symbols", [])]
            if not watchlist_symbols.intersection(article_symbols):
                continue
            try:
                news_article = NewsArticle(
                    article_id=int(article["id"]),
                    headline=str(article["headline"]),
                    summary=article.get("summary"),
                    created_at=datetime.fromisoformat(article["created_at"].replace("Z", "+00:00")),
                    updated_at=datetime.fromisoformat(article["updated_at"].replace("Z", "+00:00")),
                    symbols=article_symbols,
                    raw_data=dict(article),
                )
            except (KeyError, TypeError, ValueError):
                continue
            existing = by_id.get(news_article.article_id)
            if existing is None or news_article.updated_at > existing.updated_at:
                by_id[news_article.article_id] = news_article
        return sorted(
            by_id.values(), key=lambda article: (article.updated_at, article.article_id), reverse=True
        )

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
