"""Read-only watchlist news supplied by Alpaca."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..alpaca_market_data import AlpacaMarketDataClient, AlpacaUnavailableError, NewsArticle
from ..auth import require_api_key
from ..dependencies import get_alpaca_market_data_client, get_db
from ..models import WatchlistEntry
from ..schemas import NewsArticleOut

router = APIRouter(dependencies=[Depends(require_api_key)])


def require_alpaca(client: AlpacaMarketDataClient | None) -> AlpacaMarketDataClient:
    if client is None:
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    return client


def news_out(article: NewsArticle, watchlist_symbols: set[str]) -> NewsArticleOut:
    return NewsArticleOut(
        id=article.article_id,
        headline=article.headline,
        summary=article.summary,
        createdAt=article.created_at,
        updatedAt=article.updated_at,
        watchlistSymbols=sorted(set(article.symbols).intersection(watchlist_symbols)),
        rawData=article.raw_data,
    )


@router.get("/news", response_model=list[NewsArticleOut])
def get_watchlist_news(
    db: Session = Depends(get_db),
    client: AlpacaMarketDataClient | None = Depends(get_alpaca_market_data_client),
) -> list[NewsArticleOut]:
    """Return the latest unique Alpaca stories related to the saved watchlist only."""
    symbols = {symbol.upper() for (symbol,) in db.query(WatchlistEntry.symbol).all()}
    if not symbols:
        return []
    try:
        articles = require_alpaca(client).get_watchlist_news(sorted(symbols))
    except AlpacaUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Alpaca news is temporarily unavailable") from exc
    return [news_out(article, symbols) for article in articles]
