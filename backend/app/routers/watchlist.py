"""Read-only user watchlist routes backed by Alpaca market data."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..alpaca_market_data import AlpacaMarketDataClient
from ..auth import require_api_key
from ..config import settings
from ..dependencies import get_alpaca_market_data_client, get_db
from ..models import WatchlistEntry
from ..schemas import (
    SparklinePoint,
    WatchlistAdd,
    WatchlistEntryOut,
    WatchlistOrderUpdate,
    WatchlistQuoteOut,
    WatchlistSearchResult,
)
from ..services.watchlist import (
    WatchlistLimitError,
    add_entry,
    refresh_metadata,
    remove_entry,
    reorder_entries,
    unavailable_quote,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


def require_alpaca(client: AlpacaMarketDataClient | None) -> AlpacaMarketDataClient:
    if client is None:
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    return client


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
) -> list[WatchlistEntryOut]:
    market_data = require_alpaca(client)
    entries = db.query(WatchlistEntry).order_by(WatchlistEntry.sort_order, WatchlistEntry.added_at).all()
    refresh_metadata(db, market_data, entries)
    quotes = market_data.get_watchlist_market_data([entry.symbol for entry in entries])
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
                quote=quote_out(quotes.get(entry.symbol), market_data.feed),
            )
        )
    return result


@router.post("/watchlist", response_model=WatchlistEntryOut, status_code=201)
def add_watchlist_entry(
    payload: WatchlistAdd,
    db: Session = Depends(get_db),
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
) -> WatchlistEntryOut:
    market_data = require_alpaca(client)
    try:
        entry = add_entry(db, market_data, payload.assetId, settings.alpaca_watchlist_limit)
    except WatchlistLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    quote = unavailable_quote(market_data.feed)
    return WatchlistEntryOut(
        assetId=entry.alpaca_asset_id,
        symbol=entry.symbol,
        name=entry.name,
        exchange=entry.exchange,
        sortOrder=entry.sort_order,
        addedAt=entry.added_at,
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
        ),
    )


@router.put("/watchlist/order", status_code=204)
def update_watchlist_order(payload: WatchlistOrderUpdate, db: Session = Depends(get_db)) -> None:
    if not reorder_entries(db, payload.assetIds):
        raise HTTPException(status_code=422, detail="Order must contain every watchlist entry exactly once")


@router.delete("/watchlist/{asset_id}", status_code=204)
def delete_watchlist_entry(asset_id: str, db: Session = Depends(get_db)) -> None:
    if not remove_entry(db, asset_id):
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
