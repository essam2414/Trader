"""Behaviour of the local Alpaca IEX trade-stream module."""

import json
from datetime import datetime, timezone
from decimal import Decimal

from app.alpaca_iex_stream import AlpacaIexTradeStream, IexTrade
from app.routers.watchlist import sse_event


def test_stream_publishes_newer_trades_for_subscribed_symbols_only():
    stream = AlpacaIexTradeStream("key", "secret", max_symbols=2)
    stream.sync_symbols(["AAPL"])
    listener = stream.subscribe()

    stream._process_message(
        json.dumps(
            [
                {"T": "t", "S": "AAPL", "p": 201.25, "t": "2026-09-22T14:00:00Z"},
                {"T": "t", "S": "MSFT", "p": 501.25, "t": "2026-09-22T14:00:00Z"},
            ]
        ),
        {"AAPL"},
    )

    trade = listener.get_nowait()
    assert trade.symbol == "AAPL"
    assert trade.price == Decimal("201.25")
    assert trade.is_extended_hours is False
    assert stream.latest_trades(["AAPL", "MSFT"]) == {"AAPL": trade}

    stream._process_message(
        json.dumps([{"T": "t", "S": "AAPL", "p": 200, "t": "2026-09-22T13:59:59Z"}]),
        {"AAPL"},
    )

    assert listener.empty()
    assert stream.latest_trades(["AAPL"])["AAPL"] == trade


def test_stream_marks_trades_outside_regular_hours_as_extended():
    stream = AlpacaIexTradeStream("key", "secret", max_symbols=1)
    stream.sync_symbols(["AAPL"])
    listener = stream.subscribe()

    stream._process_message(
        json.dumps([{"T": "t", "S": "AAPL", "p": 201.25, "t": "2026-09-22T12:00:00Z"}]),
        {"AAPL"},
    )

    assert listener.get_nowait().is_extended_hours is True


def test_sse_event_exposes_only_the_quote_patch_needed_by_the_browser():
    payload = sse_event(
        IexTrade("AAPL", Decimal("201.25"), datetime(2026, 9, 22, 14, tzinfo=timezone.utc), False)
    )

    assert payload.startswith("event: quote\ndata: ")
    assert '"symbol": "AAPL"' in payload
    assert '"price": 201.25' in payload
    assert "secret" not in payload
