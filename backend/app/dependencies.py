"""Shared FastAPI dependency providers.

Wires request-scoped resources (a DB session, the Trading212 client stored on
`app.state` during the lifespan startup) into route handlers via FastAPI's
dependency injection.
"""

from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from .alpaca_iex_stream import AlpacaIexTradeStream
from .alpaca_market_data import AlpacaMarketDataClient
from .db import SessionLocal
from .services.portfolio_current import PortfolioCurrentCache
from .trading212 import Trading212Client


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session scoped to a single request, closing it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_trading212_client(request: Request) -> Trading212Client:
    """Return the shared Trading212Client instance created during app startup."""
    return request.app.state.trading212_client


def get_portfolio_current_cache(request: Request) -> PortfolioCurrentCache:
    """Return the app-wide short-lived cache for the live portfolio response."""
    return request.app.state.portfolio_current_cache


def get_alpaca_market_data_client(request: Request) -> AlpacaMarketDataClient | None:
    """Return Alpaca market data when credentials have been configured."""
    return request.app.state.alpaca_market_data_client


def get_alpaca_iex_trade_stream(request: Request) -> AlpacaIexTradeStream | None:
    """Return the app-wide IEX stream, when Alpaca credentials are configured."""
    return request.app.state.alpaca_iex_trade_stream
