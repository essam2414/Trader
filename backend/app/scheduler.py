"""Background scheduler job for periodic portfolio snapshots.

Defines the job function registered with APScheduler (in `app.main`'s
lifespan) that builds a fresh Trading212 client and DB session and delegates
to the snapshot service to capture and persist the current portfolio value.
"""

from .config import settings
from .db import SessionLocal
from .rate_limiter import trading212_rate_limiter
from .services.history_sync import sync_history
from .services.snapshot import take_snapshot
from .trading212 import Trading212Client


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
    client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
        rate_limiter=trading212_rate_limiter,
    )
    session = SessionLocal()
    try:
        account_currency = client.get_account_summary()["currency"]
        sync_history(session, client, target_currency=account_currency)
    finally:
        session.close()
