"""Selected chart streaming and watchlist selection validation."""

import json
import queue
from datetime import datetime, timezone
from decimal import Decimal

from app.alpaca_iex_stream import StreamBar, StreamTrade
from app.config import settings
from app.dependencies import get_alpaca_iex_trade_stream
from app.main import app
from app.models import WatchlistEntry
from app.routers.watchlist import multi_chart_stream_events


class FakeStream:
    is_within_limit = True

    def __init__(self):
        self.trades = queue.Queue()
        self.bars = queue.Queue()
        self.unsubscribed = []

    def subscribe(self):
        return self.trades

    def subscribe_bars(self):
        return self.bars

    def unsubscribe(self, listener):
        self.unsubscribed.append(listener)

    def unsubscribe_bars(self, listener):
        self.unsubscribed.append(listener)

    def latest_bars(self, symbols, since):
        return {}

    def latest_trades(self, symbols):
        return {}


def event_data(event: str) -> dict:
    return json.loads(event.split("data: ", 1)[1])


def test_multi_chart_stream_sends_only_selected_symbols_and_unsubscribes():
    stream = FakeStream()
    events = multi_chart_stream_events(stream, ["AAPL", "MSFT"])
    assert event_data(next(events)) == {"symbol": "AAPL", "bars": []}
    assert event_data(next(events)) == {"symbol": "MSFT", "bars": []}

    now = datetime.now(timezone.utc)
    stream.bars.put(
        StreamBar("TSLA", now, Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), 1, False, False)
    )
    stream.trades.put(StreamTrade("AAPL", Decimal("200"), now, False))
    stream.trades.put(StreamTrade("AAPL", Decimal("201.25"), now, False))
    assert event_data(next(events)) == {"symbol": "AAPL", "price": 201.25}

    stream.bars.put(
        StreamBar(
            "MSFT", now, Decimal("400"), Decimal("402"), Decimal("399"), Decimal("401"), 20, False, False
        )
    )
    bar = event_data(next(events))
    assert bar["symbol"] == "MSFT"
    assert bar["close"] == 401.0
    events.close()
    assert stream.unsubscribed == [stream.trades, stream.bars]


def test_multi_chart_stream_rejects_assets_outside_watchlist(client, db_session):
    db_session.add(
        WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ")
    )
    db_session.commit()
    app.dependency_overrides[get_alpaca_iex_trade_stream] = FakeStream
    headers = {"Authorization": f"Bearer {settings.dashboard_api_key}"}

    missing = client.get("/api/watchlist/charts/stream?assetIds=asset-aapl,asset-msft", headers=headers)
    duplicate = client.get("/api/watchlist/charts/stream?assetIds=asset-aapl,asset-aapl", headers=headers)
    empty = client.get("/api/watchlist/charts/stream?assetIds=asset-aapl,", headers=headers)

    assert missing.status_code == 404
    assert duplicate.status_code == 400
    assert empty.status_code == 400
