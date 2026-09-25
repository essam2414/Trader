"""Read-only user watchlist routes backed by Alpaca market data."""

import json
import queue
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..alpaca_iex_stream import AlpacaTradeStream, StreamBar, StreamTrade
from ..alpaca_market_data import AlpacaMarketDataClient, AlpacaUnavailableError, MarketSessionStatus
from ..auth import require_api_key
from ..config import settings
from ..dependencies import (
    get_alpaca_delayed_sip_market_data_client,
    get_alpaca_delayed_sip_trade_stream,
    get_alpaca_iex_trade_stream,
    get_alpaca_market_data_client,
    get_chart_data_source,
    get_db,
    get_trading212_client,
)
from ..models import WatchlistEntry
from ..schemas import (
    SparklinePoint,
    StockChartBarOut,
    StockChartOut,
    WatchlistAdd,
    WatchlistEntryOut,
    WatchlistOrderUpdate,
    WatchlistPositionPriceOut,
    WatchlistQuoteOut,
    WatchlistSearchResult,
)
from ..services.chart_data import CHART_RANGES, ChartDataSource, session_for
from ..services.watchlist import (
    WatchlistLimitError,
    add_entry,
    get_cached_logo,
    refresh_metadata,
    remove_entry,
    reorder_entries,
    unavailable_quote,
)
from ..trading212 import Trading212Client
from ..watchlist_price_resolver import WatchlistPriceResolver

router = APIRouter(dependencies=[Depends(require_api_key)])

# Trading212 retains SanDisk's SNDK1 instrument code; Alpaca uses SNDK.
TRADING212_SYMBOL_ALIASES = {"SNDK1": "SNDK"}


def open_position_purchase_price(positions: list[dict], symbol: str) -> tuple[float | None, str | None]:
    """Return an open position's native-currency average price for an Alpaca symbol."""
    normalized_symbol = symbol.strip().upper()
    candidate_symbols = (normalized_symbol,) + tuple(
        alias for alias, canonical in TRADING212_SYMBOL_ALIASES.items() if canonical == normalized_symbol
    )
    for candidate_symbol in candidate_symbols:
        for position in positions:
            instrument = position.get("instrument", {})
            ticker = instrument.get("ticker")
            if not isinstance(ticker, str):
                continue
            position_symbol = re.sub(r"_[^_]+_EQ$", "", ticker, flags=re.IGNORECASE).strip().upper()
            if position_symbol != candidate_symbol:
                continue
            try:
                return float(position["averagePricePaid"]), instrument.get("currency")
            except (KeyError, TypeError, ValueError):
                return None, None
    return None, None


def logo_url(asset_id: str, checked_at) -> str:
    url = f"/api/watchlist/{asset_id}/logo"
    return f"{url}?v={int(checked_at.timestamp())}" if checked_at else url


def require_alpaca(client: AlpacaMarketDataClient | None) -> AlpacaMarketDataClient:
    if client is None:
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    return client


def require_stream(stream: AlpacaTradeStream | None) -> AlpacaTradeStream:
    if stream is None:
        raise HTTPException(status_code=503, detail="Alpaca watchlist streaming is not configured")
    if not stream.is_within_limit:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Remove watchlist entries until only {settings.alpaca_watchlist_limit} remain "
                "to start IEX streaming"
            ),
        )
    return stream


def sync_stream_symbols(db: Session, *streams: AlpacaTradeStream | None) -> None:
    entries = db.query(WatchlistEntry).order_by(WatchlistEntry.sort_order, WatchlistEntry.added_at)
    symbols = [entry.symbol for entry in entries]
    for stream in streams:
        if stream is not None:
            stream.sync_symbols(symbols)


def merge_stream_trade(quote, trade: StreamTrade | None):
    """Overlay a newer stream trade while retaining its REST baseline fields."""
    if trade is None:
        return quote
    if quote is not None and quote.source_timestamp is not None and trade.timestamp < quote.source_timestamp:
        return quote
    baseline = quote or unavailable_quote(trade.feed)
    previous_close = baseline.previous_close
    dollar_change = trade.price - previous_close if previous_close is not None else None
    percent_change = (
        (dollar_change / previous_close) * 100 if dollar_change is not None and previous_close != 0 else None
    )
    return type(baseline)(
        price=trade.price,
        previous_close=previous_close,
        dollar_change=dollar_change,
        percent_change=percent_change,
        sparkline=baseline.sparkline,
        feed=trade.feed,
        source_timestamp=trade.timestamp,
        source_type=f"{trade.feed}_trade_stream",
        freshness=(
            "fresh"
            if trade.feed == "iex"
            or WatchlistPriceResolver.is_delayed_sip_current(trade.timestamp, datetime.now(timezone.utc))
            else "stale"
        ),
        is_extended_hours=trade.is_extended_hours,
    )


def select_quote(iex_quote, delayed_sip_quote, session: MarketSessionStatus | None, now: datetime):
    """Select the price source without changing the established P&L calculation."""
    if session is None:
        return iex_quote
    iex_timestamp = iex_quote.source_timestamp if iex_quote is not None else None
    feed = WatchlistPriceResolver.select_feed(session, now, iex_timestamp)
    if feed != "delayed_sip":
        return iex_quote
    if delayed_sip_quote is None:
        return unavailable_quote("delayed_sip")
    freshness = (
        "fresh"
        if WatchlistPriceResolver.is_delayed_sip_current(delayed_sip_quote.source_timestamp, now)
        else "stale"
    )
    return replace(delayed_sip_quote, freshness=freshness, is_extended_hours=True)


def sse_event(trade: StreamTrade, is_extended_hours: bool) -> str:
    """Encode the minimal state patch required by the browser watchlist."""
    return (
        "event: quote\ndata: "
        + json.dumps(
            {
                "symbol": trade.symbol,
                "price": float(trade.price),
                "feed": trade.feed,
                "sourceTimestamp": trade.timestamp.isoformat(),
                "sourceType": f"{trade.feed}_trade_stream",
                "freshness": "fresh",
                "isDelayed": trade.feed == "delayed_sip",
                "delaySeconds": 900 if trade.feed == "delayed_sip" else None,
                "isExtendedHours": is_extended_hours,
            }
        )
        + "\n\n"
    )


def chart_bar_payload(bar: StreamBar) -> dict[str, object]:
    return {
        "startsAt": bar.starts_at.isoformat(),
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": bar.volume,
        "session": session_for(bar.starts_at),
        "isUpdated": bar.is_updated,
        "feed": bar.feed,
    }


def chart_stream_events(stream: AlpacaTradeStream, symbol: str) -> Iterator[str]:
    """Expose the rolling IEX cache first, then completed/corrected bars and trades."""
    trade_listener = stream.subscribe()
    bar_listener = stream.subscribe_bars()
    try:
        initial_bars = stream.latest_bars([symbol], datetime.now(timezone.utc) - timedelta(minutes=20))
        initial_trade = stream.latest_trades([symbol]).get(symbol)
        snapshot: dict[str, object] = {
            "bars": [chart_bar_payload(bar) for bar in initial_bars.get(symbol, [])]
        }
        if initial_trade is not None:
            snapshot["latestTrade"] = {
                "price": float(initial_trade.price),
                "timestamp": initial_trade.timestamp.isoformat(),
            }
        yield "event: live_snapshot\ndata: " + json.dumps(snapshot) + "\n\n"
        while True:
            try:
                bar = bar_listener.get(timeout=0.25)
                if bar.symbol == symbol:
                    yield "event: bar\ndata: " + json.dumps(chart_bar_payload(bar)) + "\n\n"
            except queue.Empty:
                pass
            try:
                trade = trade_listener.get_nowait()
                if trade.symbol == symbol:
                    yield (
                        "event: trade\ndata: "
                        + json.dumps({"price": float(trade.price), "timestamp": trade.timestamp.isoformat()})
                        + "\n\n"
                    )
            except queue.Empty:
                pass
    finally:
        stream.unsubscribe(trade_listener)
        stream.unsubscribe_bars(bar_listener)


def _selected_trade(
    iex_stream: AlpacaTradeStream,
    delayed_sip_stream: AlpacaTradeStream,
    symbol: str,
    session: MarketSessionStatus,
    now: datetime,
) -> StreamTrade | None:
    iex_trade = iex_stream.latest_trades([symbol]).get(symbol)
    feed = WatchlistPriceResolver.select_feed(session, now, iex_trade.timestamp if iex_trade else None)
    if feed == "iex":
        return iex_trade
    if feed == "delayed_sip":
        return delayed_sip_stream.latest_trades([symbol]).get(symbol)
    return None


def stream_events(
    iex_stream: AlpacaTradeStream,
    delayed_sip_stream: AlpacaTradeStream,
    market_data: AlpacaMarketDataClient,
) -> Iterator[str]:
    """Yield selected IEX or delayed-SIP quote events with transition updates."""
    listeners = (iex_stream.subscribe(), delayed_sip_stream.subscribe())
    last_selected_trades: dict[str, tuple[str, datetime]] = {}
    last_keepalive = time.monotonic()
    try:
        yield ": connected\n\n"
        while True:
            now = datetime.now(timezone.utc)
            try:
                session = market_data.get_market_session(now)
            except AlpacaUnavailableError:
                session = None
            if session is not None:
                symbols = set(iex_stream.symbols()) | set(delayed_sip_stream.symbols())
                for symbol in sorted(symbols):
                    trade = _selected_trade(iex_stream, delayed_sip_stream, symbol, session, now)
                    if trade is None:
                        continue
                    selection = (trade.feed, trade.timestamp)
                    if last_selected_trades.get(symbol) != selection:
                        last_selected_trades[symbol] = selection
                        yield sse_event(trade, session.phase != "regular")
                for listener in listeners:
                    try:
                        listener.get(timeout=0.25)
                    except queue.Empty:
                        continue
            if time.monotonic() - last_keepalive >= 15:
                yield ": keepalive\n\n"
                last_keepalive = time.monotonic()
    finally:
        iex_stream.unsubscribe(listeners[0])
        delayed_sip_stream.unsubscribe(listeners[1])


def quote_out(quote, feed: str) -> WatchlistQuoteOut:
    """Turn a possibly unavailable provider quote into the frontend contract."""
    market_quote = quote or unavailable_quote(feed)
    return WatchlistQuoteOut(
        price=float(market_quote.price) if market_quote.price is not None else None,
        previousClose=float(market_quote.previous_close) if market_quote.previous_close is not None else None,
        dollarChange=float(market_quote.dollar_change) if market_quote.dollar_change is not None else None,
        percentChange=float(market_quote.percent_change) if market_quote.percent_change is not None else None,
        sparkline=[
            SparklinePoint(timestamp=point.timestamp, close=float(point.close))
            for point in market_quote.sparkline
        ],
        feed=market_quote.feed,
        sourceTimestamp=market_quote.source_timestamp,
        sourceType=market_quote.source_type,
        freshness=market_quote.freshness,
        isExtendedHours=market_quote.is_extended_hours,
        isDelayed=market_quote.feed == "delayed_sip",
        delaySeconds=900 if market_quote.feed == "delayed_sip" else None,
    )


@router.get("/watchlist/search", response_model=list[WatchlistSearchResult])
def search_watchlist_assets(
    q: str = Query(min_length=1, max_length=100),
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
) -> list[WatchlistSearchResult]:
    market_data = require_alpaca(client)
    return [
        WatchlistSearchResult(
            assetId=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            exchange=asset.exchange,
        )
        for asset in market_data.search_us_equities(q)
    ]


@router.get("/watchlist", response_model=list[WatchlistEntryOut])
def get_watchlist(
    db: Session = Depends(get_db),
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
    delayed_sip_client: AlpacaMarketDataClient | None = Depends(get_alpaca_delayed_sip_market_data_client),
    stream: AlpacaTradeStream | None = Depends(get_alpaca_iex_trade_stream),
    delayed_sip_stream: AlpacaTradeStream | None = Depends(get_alpaca_delayed_sip_trade_stream),
) -> list[WatchlistEntryOut]:
    market_data = require_alpaca(client)
    entries = db.query(WatchlistEntry).order_by(WatchlistEntry.sort_order, WatchlistEntry.added_at).all()
    refresh_metadata(db, market_data, entries)
    quotes = market_data.get_watchlist_market_data([entry.symbol for entry in entries])
    latest_trades = stream.latest_trades([entry.symbol for entry in entries]) if stream else {}
    try:
        session = market_data.get_market_session()
    except AlpacaUnavailableError:
        session = None
    delayed_quotes = (
        delayed_sip_client.get_watchlist_market_data([entry.symbol for entry in entries])
        if delayed_sip_client is not None
        and session is not None
        and session.phase in {"pre_market", "after_hours"}
        else {}
    )
    delayed_trades = (
        delayed_sip_stream.latest_trades([entry.symbol for entry in entries]) if delayed_sip_stream else {}
    )
    now = datetime.now(timezone.utc)
    result: list[WatchlistEntryOut] = []
    for entry in entries:
        result.append(
            WatchlistEntryOut(
                assetId=entry.alpaca_asset_id,
                symbol=entry.symbol,
                name=entry.name,
                exchange=entry.exchange,
                sortOrder=entry.sort_order,
                addedAt=entry.added_at,
                logoUrl=logo_url(entry.alpaca_asset_id, entry.logo_checked_at),
                quote=quote_out(
                    select_quote(
                        merge_stream_trade(quotes.get(entry.symbol), latest_trades.get(entry.symbol)),
                        merge_stream_trade(
                            delayed_quotes.get(entry.symbol), delayed_trades.get(entry.symbol)
                        ),
                        session,
                        now,
                    ),
                    "iex",
                ),
            )
        )
    return result


@router.get("/watchlist/{asset_id}/position", response_model=WatchlistPositionPriceOut)
def get_watchlist_position_price(
    asset_id: str,
    db: Session = Depends(get_db),
    trading212_client: Trading212Client = Depends(get_trading212_client),
) -> WatchlistPositionPriceOut:
    """Fetch the open-position level independently of market data and chart range."""
    entry = db.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    try:
        price, currency = open_position_purchase_price(trading212_client.get_positions(), entry.symbol)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise HTTPException(status_code=502, detail="Could not load open position") from exc
    return WatchlistPositionPriceOut(purchasePrice=price, purchasePriceCurrency=currency)


@router.get("/watchlist/{asset_id}/chart", response_model=StockChartOut)
def get_stock_chart(
    asset_id: str,
    range: str = Query(default="1D", pattern="^(1D|1W|1M|3M|1Y|MAX)$"),
    db: Session = Depends(get_db),
    chart_data_source: ChartDataSource | None = Depends(get_chart_data_source),
) -> StockChartOut:
    """Return on-demand delayed SIP history plus a visibly separate live IEX tail."""
    entry = db.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    if chart_data_source is None:
        raise HTTPException(status_code=503, detail="Alpaca chart data is not configured")
    chart_range = CHART_RANGES[range]
    now = datetime.now(timezone.utc)
    try:
        snapshot = chart_data_source.load_chart(entry, chart_range, now)
    except AlpacaUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Stock chart data is temporarily unavailable") from exc

    def output(bar) -> StockChartBarOut:
        return StockChartBarOut(
            startsAt=bar.starts_at,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=bar.volume,
            session=bar.session,
        )

    return StockChartOut(
        assetId=entry.alpaca_asset_id,
        symbol=entry.symbol,
        name=entry.name,
        range=range,
        intervalSeconds=chart_range.output_interval_seconds,
        canonicalFeed="sip",
        adjustment="raw",
        canonicalThrough=snapshot.canonical_through,
        delaySeconds=900,
        canonicalBars=[output(bar) for bar in snapshot.canonical_bars],
        provisionalIexBars=[output(bar) for bar in snapshot.provisional_iex_bars],
    )


@router.get("/watchlist/{asset_id}/chart/stream")
def stream_stock_chart(
    asset_id: str,
    db: Session = Depends(get_db),
    stream: AlpacaTradeStream | None = Depends(get_alpaca_iex_trade_stream),
) -> StreamingResponse:
    entry = db.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    return StreamingResponse(
        chart_stream_events(require_stream(stream), entry.symbol),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/watchlist", response_model=WatchlistEntryOut, status_code=201)
def add_watchlist_entry(
    payload: WatchlistAdd,
    db: Session = Depends(get_db),
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
    stream: AlpacaTradeStream | None = Depends(get_alpaca_iex_trade_stream),
    delayed_sip_stream: AlpacaTradeStream | None = Depends(get_alpaca_delayed_sip_trade_stream),
) -> WatchlistEntryOut:
    market_data = require_alpaca(client)
    try:
        entry = add_entry(db, market_data, payload.assetId, settings.alpaca_watchlist_limit)
    except WatchlistLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    sync_stream_symbols(db, stream, delayed_sip_stream)
    quote = unavailable_quote(market_data.feed)
    return WatchlistEntryOut(
        assetId=entry.alpaca_asset_id,
        symbol=entry.symbol,
        name=entry.name,
        exchange=entry.exchange,
        sortOrder=entry.sort_order,
        addedAt=entry.added_at,
        logoUrl=logo_url(entry.alpaca_asset_id, entry.logo_checked_at),
        quote=WatchlistQuoteOut(
            price=None,
            previousClose=None,
            dollarChange=None,
            percentChange=None,
            sparkline=[],
            feed=quote.feed,
            sourceTimestamp=None,
            sourceType=None,
            freshness="unavailable",
            isExtendedHours=False,
            isDelayed=False,
            delaySeconds=None,
        ),
    )


@router.get("/watchlist/stream")
def stream_watchlist_quotes(
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
    stream: AlpacaTradeStream | None = Depends(get_alpaca_iex_trade_stream),
    delayed_sip_stream: AlpacaTradeStream | None = Depends(get_alpaca_delayed_sip_trade_stream),
) -> StreamingResponse:
    """Relay the selected IEX or delayed-SIP stream to browser clients."""
    return StreamingResponse(
        stream_events(require_stream(stream), require_stream(delayed_sip_stream), require_alpaca(client)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/watchlist/{asset_id}/logo")
def get_watchlist_logo(
    asset_id: str,
    db: Session = Depends(get_db),
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
) -> Response:
    entry = db.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    logo = get_cached_logo(db, require_alpaca(client), entry)
    if logo is None:
        raise HTTPException(status_code=404, detail="Company logo is unavailable")
    logo_data, content_type = logo
    return Response(
        content=logo_data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=604800, immutable"},
    )


@router.put("/watchlist/order", status_code=204)
def update_watchlist_order(payload: WatchlistOrderUpdate, db: Session = Depends(get_db)) -> None:
    if not reorder_entries(db, payload.assetIds):
        raise HTTPException(status_code=422, detail="Order must contain every watchlist entry exactly once")


@router.delete("/watchlist/{asset_id}", status_code=204)
def delete_watchlist_entry(
    asset_id: str,
    db: Session = Depends(get_db),
    stream: AlpacaTradeStream | None = Depends(get_alpaca_iex_trade_stream),
    delayed_sip_stream: AlpacaTradeStream | None = Depends(get_alpaca_delayed_sip_trade_stream),
) -> None:
    if not remove_entry(db, asset_id):
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    sync_stream_symbols(db, stream, delayed_sip_stream)
