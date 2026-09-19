"""Database engine and session plumbing.

Sets up the SQLAlchemy engine and session factory used throughout the app,
driven by `settings.database_url` (a local SQLite file by default, a
Postgres/Supabase URL in production). `Base` is the declarative base that
all ORM models (see `app/models.py`) inherit from.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
