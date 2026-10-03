"""FastAPI application entrypoint.

Defines the `app` instance, the lifespan context manager (creates DB tables,
constructs the shared Trading212 client on `app.state`, and starts the
background scheduler that periodically snapshots the portfolio), and mounts
the portfolio router plus the top-level `/health` route.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from .alpaca_iex_stream import AlpacaIexTradeStream
from .alpaca_market_data import AlpacaMarketDataClient
from .config import settings
from .db import Base, SessionLocal, engine
from .models import WatchlistEntry
from .rate_limiter import trading212_rate_limiter
from .routers.market_session import router as market_session_router
from .routers.news import router as news_router
from .routers.portfolio import router as portfolio_router
from .routers.watchlist import router as watchlist_router
from .scheduler import (
    news_jobs_due,
    run_events_job,
    run_history_sync_job,
    run_news_job,
    run_pending_news_job,
    run_snapshot_job,
)
from .services.chart_data import AlpacaChartDataSource
from .services.portfolio_current import PortfolioCurrentCache
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
        rate_limiter=trading212_rate_limiter,
    )
    app.state.portfolio_current_cache = PortfolioCurrentCache()
    app.state.alpaca_market_data_client = (
        AlpacaMarketDataClient(settings.alpaca_api_key, settings.alpaca_api_secret, settings.alpaca_data_feed)
        if settings.alpaca_api_key and settings.alpaca_api_secret
        else None
    )
    app.state.alpaca_delayed_sip_market_data_client = (
        AlpacaMarketDataClient(settings.alpaca_api_key, settings.alpaca_api_secret, "delayed_sip")
        if settings.alpaca_api_key and settings.alpaca_api_secret
        else None
    )
    app.state.chart_data_source = (
        AlpacaChartDataSource(
            AlpacaMarketDataClient(settings.alpaca_api_key, settings.alpaca_api_secret, "sip"),
            AlpacaMarketDataClient(settings.alpaca_api_key, settings.alpaca_api_secret, "iex"),
        )
        if settings.alpaca_api_key and settings.alpaca_api_secret
        else None
    )
    app.state.alpaca_iex_trade_stream = None
    app.state.alpaca_delayed_sip_trade_stream = None
    if settings.alpaca_api_key and settings.alpaca_api_secret:
        stream = AlpacaIexTradeStream(
            settings.alpaca_api_key, settings.alpaca_api_secret, settings.alpaca_watchlist_limit
        )
        session = SessionLocal()
        try:
            watchlist_symbols = [
                entry.symbol for entry in session.query(WatchlistEntry).order_by(WatchlistEntry.sort_order)
            ]
        finally:
            session.close()
        stream.sync_symbols(watchlist_symbols)
        stream.start()
        app.state.alpaca_iex_trade_stream = stream
        delayed_sip_stream = AlpacaIexTradeStream(
            settings.alpaca_api_key,
            settings.alpaca_api_secret,
            settings.alpaca_watchlist_limit,
            feed="delayed_sip",
        )
        delayed_sip_stream.sync_symbols(watchlist_symbols)
        delayed_sip_stream.start()
        app.state.alpaca_delayed_sip_trade_stream = delayed_sip_stream
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_snapshot_job, "interval", minutes=settings.snapshot_interval_minutes)
    scheduler.add_job(run_history_sync_job, "interval", minutes=settings.history_sync_interval_minutes)
    if settings.news_enabled:
        eastern = ZoneInfo("America/New_York")
        scheduler.add_job(
            run_pending_news_job,
            "interval",
            minutes=5,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=15),
            id="news_pending_summaries",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_news_job,
            CronTrigger(
                hour=settings.news_morning_hour_et, minute=settings.news_morning_minute_et, timezone=eastern
            ),
            id="news_morning",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_news_job,
            CronTrigger(
                hour=settings.news_evening_hour_et, minute=settings.news_evening_minute_et, timezone=eastern
            ),
            id="news_evening",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_events_job,
            CronTrigger(hour=6, minute=0, timezone=eastern),
            id="events_daily",
            max_instances=1,
            coalesce=True,
        )
        news_due, events_due = news_jobs_due()
        soon = datetime.now(timezone.utc) + timedelta(seconds=5)
        if news_due:
            scheduler.add_job(run_news_job, "date", run_date=soon, id="news_catchup")
        if events_due:
            scheduler.add_job(
                run_events_job, "date", run_date=soon + timedelta(seconds=2), id="events_catchup"
            )
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()
    if app.state.alpaca_iex_trade_stream is not None:
        app.state.alpaca_iex_trade_stream.stop()
    if app.state.alpaca_delayed_sip_trade_stream is not None:
        app.state.alpaca_delayed_sip_trade_stream.stop()


app = FastAPI(title="Trader API", lifespan=lifespan)
app.include_router(portfolio_router, prefix="/api")
app.include_router(market_session_router, prefix="/api")
app.include_router(news_router, prefix="/api")
app.include_router(watchlist_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by deployment platforms/monitoring to confirm the API is up."""
    return {"status": "ok"}
