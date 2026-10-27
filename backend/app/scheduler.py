"""Background scheduler job for periodic portfolio snapshots.

Defines the job function registered with APScheduler (in `app.main`'s
lifespan) that builds a fresh Trading212 client and DB session and delegates
to the snapshot service to capture and persist the current portfolio value.
"""

import time
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import text as sql_text

from .config import settings
from .db import SessionLocal, engine
from .rate_limiter import trading212_rate_limiter
from .services.history_sync import HISTORY_SYNC_TIME_BUDGET_SECONDS, sync_history
from .services.snapshot import take_snapshot
from .trading212 import Trading212Client

_digest_locks = {"news": Lock(), "events": Lock()}
_advisory_keys = {"news": 27182818, "events": 27182819}


def _run_digest_job(job: str, *, force: bool = False) -> dict[str, int] | None:
    lock_key = "news" if job == "news_pending" else job
    lock = _digest_locks[lock_key]
    if not settings.news_enabled or not lock.acquire(blocking=False):
        return None
    session = SessionLocal()
    lock_connection = None
    advisory_locked = False
    try:
        if engine.dialect.name == "postgresql":
            lock_connection = engine.connect()
            advisory_locked = bool(
                lock_connection.execute(
                    sql_text("SELECT pg_try_advisory_lock(:key)"), {"key": _advisory_keys[lock_key]}
                ).scalar()
            )
            if not advisory_locked:
                return
        if job == "news":
            from .services.news_digest import run_news_sync

            return run_news_sync(session, force=force)
        if job == "news_pending":
            from .services.news_digest import run_pending_analysis

            return {"pending_retried": run_pending_analysis(session)}
        else:
            from .services.news_events import run_events_sync

            return run_events_sync(session)
    finally:
        if advisory_locked:
            lock_connection.execute(
                sql_text("SELECT pg_advisory_unlock(:key)"), {"key": _advisory_keys[lock_key]}
            )
        if lock_connection is not None:
            lock_connection.close()
        session.close()
        lock.release()


def run_news_job(*, force: bool = False) -> dict[str, int] | None:
    return _run_digest_job("news", force=force)


def run_pending_news_job() -> dict[str, int] | None:
    return _run_digest_job("news_pending")


def run_events_job() -> dict[str, int] | None:
    return _run_digest_job("events")


def news_jobs_due() -> tuple[bool, bool]:
    """Catch up after the desktop app was closed during a scheduled briefing."""
    from .models import NewsSyncState

    now = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        news = (
            session.query(NewsSyncState.last_success_at)
            .filter(
                ~NewsSyncState.source_key.startswith("events:"),
                NewsSyncState.last_success_at.is_not(None),
            )
            .order_by(NewsSyncState.last_success_at.desc())
            .first()
        )
        events = (
            session.query(NewsSyncState.last_success_at)
            .filter(
                NewsSyncState.source_key.startswith("events:"),
                NewsSyncState.last_success_at.is_not(None),
            )
            .order_by(NewsSyncState.last_success_at.desc())
            .first()
        )

        def age_seconds(value: datetime | None) -> float:
            if value is None:
                return float("inf")
            aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            return (now - aware).total_seconds()

        return age_seconds(news[0] if news else None) > 13 * 3600, age_seconds(
            events[0] if events else None
        ) > 24 * 3600
    finally:
        session.close()


def run_snapshot_job() -> None:
    """Take and persist a portfolio snapshot; invoked on a timer by the scheduler."""
    client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
        rate_limiter=trading212_rate_limiter,
    )
    session = SessionLocal()
    try:
        take_snapshot(session, client)
    finally:
        session.close()


def run_history_sync_job() -> None:
    """Sync Trading212 order/dividend history; invoked on a timer by the scheduler.

    Fetches the account summary first to get the account's base currency, so
    fills that settled in a different currency get normalized to it.
    """
    started_at = time.monotonic()
    client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
        rate_limiter=trading212_rate_limiter,
    )
    session = SessionLocal()
    try:
        account_currency = client.get_account_summary()["currency"]
        sync_history(
            session,
            client,
            target_currency=account_currency,
            deadline=started_at + HISTORY_SYNC_TIME_BUDGET_SECONDS,
        )
    finally:
        session.close()
