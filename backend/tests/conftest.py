"""Shared pytest fixtures for the backend test suite.

Sets required env vars before any app module is imported (so `app.config`
can construct `Settings` without hitting real credentials), and provides
the `db_session` fixture that DB-touching tests use.
"""
import os

os.environ.setdefault("TRADING212_API_KEY", "test-api-key")
os.environ.setdefault("TRADING212_API_SECRET", "test-api-secret")
os.environ.setdefault("DASHBOARD_API_KEY", "test-dashboard-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base


@pytest.fixture()
def db_session():
    """Provide an isolated in-memory SQLite session, fresh per test.

    Creates a new engine/schema for each test so tests never share state or
    leak data between runs, then tears the session down afterward.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
