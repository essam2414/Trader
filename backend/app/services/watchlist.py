"""Persistence and presentation assembly for the dashboard watchlist."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.alpaca_market_data import AlpacaMarketDataClient, MarketQuote
from app.models import WatchlistEntry


class WatchlistLimitError(ValueError):
    """Raised when adding an entry would exceed the configured limit."""


LOGO_RECHECK_INTERVAL = timedelta(days=7)
LOGO_PROVIDER = "eulerpool"


def add_entry(session, client: AlpacaMarketDataClient, asset_id: str, limit: int) -> WatchlistEntry:
    existing = session.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
    if existing:
        return existing
    if session.query(WatchlistEntry).count() >= limit:
        raise WatchlistLimitError(f"Watchlist is limited to {limit} equities")
    asset = client.get_asset(asset_id)
    if asset is None:
        raise LookupError("The selected Alpaca US equity is no longer active")
    last_order = session.query(func.max(WatchlistEntry.sort_order)).scalar()
    entry = WatchlistEntry(
        alpaca_asset_id=asset.asset_id,
        symbol=asset.symbol,
        name=asset.name,
        exchange=asset.exchange,
        sort_order=(last_order + 1) if last_order is not None else 0,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def remove_entry(session, asset_id: str) -> bool:
    entry = session.query(WatchlistEntry).filter_by(alpaca_asset_id=asset_id).one_or_none()
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def reorder_entries(session, asset_ids: list[str]) -> bool:
    """Persist one complete, duplicate-free ordering of the current watchlist."""
    entries = session.query(WatchlistEntry).all()
    current_ids = {entry.alpaca_asset_id for entry in entries}
    if len(asset_ids) != len(set(asset_ids)) or set(asset_ids) != current_ids:
        return False
    by_asset_id = {entry.alpaca_asset_id: entry for entry in entries}
    for sort_order, asset_id in enumerate(asset_ids):
        by_asset_id[asset_id].sort_order = sort_order
    session.commit()
    return True


def refresh_metadata(session, client: AlpacaMarketDataClient, entries: list[WatchlistEntry]) -> None:
    changed = False
    catalog = {asset.asset_id: asset for asset in client._load_catalog()}
    for entry in entries:
        asset = catalog.get(entry.alpaca_asset_id)
        if asset and (entry.symbol, entry.name, entry.exchange) != (asset.symbol, asset.name, asset.exchange):
            entry.symbol, entry.name, entry.exchange = asset.symbol, asset.name, asset.exchange
            changed = True
    if changed:
        session.commit()


def get_cached_logo(
    session, client: AlpacaMarketDataClient, entry: WatchlistEntry
) -> tuple[bytes, str] | None:
    """Return the persisted logo, fetching it once from Alpaca when needed.

    Failed lookups are recorded too, avoiding a provider call for every page refresh
    when an asset does not have a logo in Alpaca's catalogue.
    """
    if entry.logo_data and entry.logo_content_type:
        return entry.logo_data, entry.logo_content_type

    now = datetime.now(timezone.utc)
    if (
        entry.logo_provider == LOGO_PROVIDER
        and entry.logo_checked_at
        and now - entry.logo_checked_at <= LOGO_RECHECK_INTERVAL
    ):
        return None

    entry.logo_provider = LOGO_PROVIDER
    entry.logo_checked_at = now
    try:
        logo = client.get_company_logo(entry.symbol)
    except Exception:
        session.commit()
        return None
    if logo is not None:
        entry.logo_data, entry.logo_content_type = logo
    session.commit()
    return logo


def unavailable_quote(feed: str) -> MarketQuote:
    return MarketQuote(None, None, None, None, [], feed, None, None, "unavailable", False)
