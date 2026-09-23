"""A shared Alpaca IEX trade stream for the local dashboard watchlist."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from websockets.asyncio.client import connect

from .alpaca_market_data import NEW_YORK

LOGGER = logging.getLogger(__name__)
STREAM_BASE_URL = "wss://stream.data.alpaca.markets/v2"
RECONNECT_DELAY_SECONDS = 1
MAX_RECONNECT_DELAY_SECONDS = 30


@dataclass(frozen=True)
class StreamTrade:
    """The latest usable trade for a subscribed watchlist symbol."""

    symbol: str
    price: Decimal
    timestamp: datetime
    is_extended_hours: bool
    feed: str = "iex"


@dataclass(frozen=True)
class StreamBar:
    """A completed or corrected provider minute bar retained only for live display."""

    symbol: str
    starts_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_extended_hours: bool
    is_updated: bool
    feed: str = "iex"


class AlpacaTradeStream:
    """Keep one authenticated Alpaca trade stream and fan trades out locally.

    Callers only need to synchronise the persisted watchlist symbols, read the
    latest trade cache, or subscribe to quote events. Connection, reconnect and
    subscription details remain inside this module.
    """

    def __init__(self, api_key: str, api_secret: str, max_symbols: int, feed: str = "iex") -> None:
        if feed not in {"iex", "delayed_sip"}:
            raise ValueError("stream feed must be iex or delayed_sip")
        self._api_key = api_key
        self._api_secret = api_secret
        self._max_symbols = max_symbols
        self.feed = feed
        self._symbols: set[str] = set()
        self._trades: dict[str, StreamTrade] = {}
        self._bars: dict[str, dict[datetime, StreamBar]] = {}
        self._listeners: set[queue.Queue[StreamTrade]] = set()
        self._bar_listeners: set[queue.Queue[StreamBar]] = set()
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._symbols_changed = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_within_limit(self) -> bool:
        with self._lock:
            return len(self._symbols) <= self._max_symbols

    def start(self) -> None:
        """Start the single background stream thread once."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(target=self._run, name=f"alpaca-{self.feed}-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the stream to stop and wait briefly for its connection to close."""
        self._stop_requested.set()
        self._symbols_changed.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def sync_symbols(self, symbols: list[str]) -> None:
        """Replace the stream subscription set with the persisted watchlist."""
        normalized = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        with self._lock:
            if normalized == self._symbols:
                return
            self._symbols = normalized
            self._trades = {symbol: trade for symbol, trade in self._trades.items() if symbol in normalized}
            self._bars = {symbol: bars for symbol, bars in self._bars.items() if symbol in normalized}
        self._symbols_changed.set()

    def latest_trades(self, symbols: list[str]) -> dict[str, StreamTrade]:
        """Return only currently retained trades for the requested symbols."""
        with self._lock:
            return {symbol: self._trades[symbol] for symbol in symbols if symbol in self._trades}

    def symbols(self) -> list[str]:
        """Return the current subscription set for source-transition events."""
        with self._lock:
            return sorted(self._symbols)

    def latest_bars(self, symbols: list[str], since: datetime | None = None) -> dict[str, list[StreamBar]]:
        """Return the small rolling live cache, including late-bar corrections."""
        with self._lock:
            return {
                symbol: [
                    bar
                    for stamp, bar in sorted(self._bars.get(symbol, {}).items())
                    if since is None or stamp >= since
                ]
                for symbol in symbols
            }

    def subscribe(self) -> queue.Queue[StreamTrade]:
        """Register one local SSE consumer for future trade events."""
        listener: queue.Queue[StreamTrade] = queue.Queue(maxsize=100)
        with self._lock:
            self._listeners.add(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue[StreamTrade]) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def subscribe_bars(self) -> queue.Queue[StreamBar]:
        listener: queue.Queue[StreamBar] = queue.Queue(maxsize=100)
        with self._lock:
            self._bar_listeners.add(listener)
        return listener

    def unsubscribe_bars(self, listener: queue.Queue[StreamBar]) -> None:
        with self._lock:
            self._bar_listeners.discard(listener)

    def _run(self) -> None:
        asyncio.run(self._run_forever())

    async def _run_forever(self) -> None:
        delay = RECONNECT_DELAY_SECONDS
        while not self._stop_requested.is_set():
            symbols = self._current_symbols()
            if not symbols or len(symbols) > self._max_symbols:
                self._symbols_changed.wait(timeout=1)
                self._symbols_changed.clear()
                continue
            try:
                async with connect(
                    f"{STREAM_BASE_URL}/{self.feed}", open_timeout=10, close_timeout=5
                ) as socket:
                    await socket.recv()  # Alpaca's connected acknowledgement.
                    await socket.send(
                        json.dumps({"action": "auth", "key": self._api_key, "secret": self._api_secret})
                    )
                    await socket.recv()  # Authentication acknowledgement or error.
                    await socket.send(
                        json.dumps(
                            {
                                "action": "subscribe",
                                "trades": sorted(symbols),
                                "bars": sorted(symbols),
                                "updatedBars": sorted(symbols),
                            }
                        )
                    )
                    delay = RECONNECT_DELAY_SECONDS
                    await self._receive_until_symbols_change(socket, symbols)
            except Exception:  # The stream must recover from transient network/provider failures.
                if not self._stop_requested.is_set():
                    LOGGER.warning("Alpaca IEX stream disconnected; reconnecting in %s seconds", delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, MAX_RECONNECT_DELAY_SECONDS)

    async def _receive_until_symbols_change(self, socket, subscribed_symbols: set[str]) -> None:
        while not self._stop_requested.is_set():
            if self._symbols_changed.is_set():
                self._symbols_changed.clear()
                if self._current_symbols() != subscribed_symbols:
                    return
            try:
                message = await asyncio.wait_for(socket.recv(), timeout=1)
            except TimeoutError:
                continue
            self._process_message(message, subscribed_symbols)

    def _process_message(self, message: str | bytes, subscribed_symbols: set[str]) -> None:
        try:
            events = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(events, list):
            return
        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = event.get("T")
            symbol = str(event.get("S", "")).upper()
            if symbol not in subscribed_symbols:
                continue
            if event_type == "t":
                self._process_trade_event(symbol, event)
            elif event_type in {"b", "u"}:
                self._process_bar_event(symbol, event, is_updated=event_type == "u")

    def _process_trade_event(self, symbol: str, event: dict) -> None:
        try:
            timestamp = datetime.fromisoformat(str(event["t"]).replace("Z", "+00:00"))
            trade = StreamTrade(
                symbol=symbol,
                price=Decimal(str(event["p"])),
                timestamp=timestamp,
                is_extended_hours=not self._is_regular_session(timestamp),
                feed=self.feed,
            )
        except (KeyError, TypeError, ValueError):
            return
        self._record_trade(trade)

    def _process_bar_event(self, symbol: str, event: dict, is_updated: bool) -> None:
        try:
            starts_at = datetime.fromisoformat(str(event["t"]).replace("Z", "+00:00"))
            bar = StreamBar(
                symbol=symbol,
                starts_at=starts_at,
                open=Decimal(str(event["o"])),
                high=Decimal(str(event["h"])),
                low=Decimal(str(event["l"])),
                close=Decimal(str(event["c"])),
                volume=int(event["v"]),
                is_extended_hours=not self._is_regular_session(starts_at),
                is_updated=is_updated,
                feed=self.feed,
            )
        except (KeyError, TypeError, ValueError):
            return
        self._record_bar(bar)

    @staticmethod
    def _is_regular_session(timestamp: datetime) -> bool:
        new_york = timestamp.astimezone(NEW_YORK)
        return (
            new_york.weekday() < 5
            and (new_york.hour, new_york.minute) >= (9, 30)
            and (
                new_york.hour,
                new_york.minute,
            )
            < (16, 0)
        )

    def _record_trade(self, trade: StreamTrade) -> None:
        with self._lock:
            previous = self._trades.get(trade.symbol)
            if previous is not None and trade.timestamp <= previous.timestamp:
                return
            self._trades[trade.symbol] = trade
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener.put_nowait(trade)
            except queue.Full:
                try:
                    listener.get_nowait()
                    listener.put_nowait(trade)
                except (queue.Empty, queue.Full):
                    pass

    def _record_bar(self, bar: StreamBar) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=20)
        with self._lock:
            bars = self._bars.setdefault(bar.symbol, {})
            bars[bar.starts_at] = bar
            self._bars[bar.symbol] = {stamp: value for stamp, value in bars.items() if stamp >= cutoff}
            listeners = tuple(self._bar_listeners)
        for listener in listeners:
            try:
                listener.put_nowait(bar)
            except queue.Full:
                try:
                    listener.get_nowait()
                    listener.put_nowait(bar)
                except (queue.Empty, queue.Full):
                    pass

    def _current_symbols(self) -> set[str]:
        with self._lock:
            return set(self._symbols)


# Backwards-compatible names for the existing IEX-only callers and tests.
IexTrade = StreamTrade
AlpacaIexTradeStream = AlpacaTradeStream
