"""FastAPI application entrypoint.

Defines the `app` instance, the lifespan context manager (creates DB tables,
constructs the shared Trading212 client on `app.state`, and starts the
background scheduler that periodically snapshots the portfolio), and mounts
the portfolio router plus the top-level `/health` route.
"""

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from .config import settings
from .db import Base, engine
from .routers.portfolio import router as portfolio_router
from .scheduler import run_snapshot_job
from .trading212 import Trading212Client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app startup/shutdown: create tables, wire up the Trading212
    client and background scheduler on app startup, and shut the scheduler
    down cleanly on app shutdown."""
    Base.metadata.create_all(bind=engine)
    app.state.trading212_client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
    )
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_snapshot_job, "interval", minutes=settings.snapshot_interval_minutes)
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Trader API", lifespan=lifespan)
app.include_router(portfolio_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by deployment platforms/monitoring to confirm the API is up."""
    return {"status": "ok"}
