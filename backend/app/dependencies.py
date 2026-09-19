"""Shared FastAPI dependency providers.

Wires request-scoped resources (a DB session, the Trading212 client stored on
`app.state` during the lifespan startup) into route handlers via FastAPI's
dependency injection.
"""

from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from .db import SessionLocal
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
