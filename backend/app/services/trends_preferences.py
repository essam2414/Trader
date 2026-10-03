"""Database persistence for the shared Trends selection, order and chart range."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import TrendsPreferences, WatchlistEntry
from ..schemas import TrendsPreferencesOut, TrendsPreferencesUpdate


def load_preferences(db: Session) -> TrendsPreferencesOut:
    preferences = db.get(TrendsPreferences, 1)
    available = {asset_id for (asset_id,) in db.query(WatchlistEntry.alpaca_asset_id)}
    return TrendsPreferencesOut(
        assetIds=[asset_id for asset_id in preferences.asset_ids if asset_id in available]
        if preferences
        else [],
        range=preferences.chart_range if preferences else "1W",
        initialized=preferences is not None,
    )


def save_preferences(
    db: Session, update: TrendsPreferencesUpdate, *, initialize_only: bool = False
) -> TrendsPreferencesOut:
    preferences = db.get(TrendsPreferences, 1, with_for_update=True)
    if initialize_only and preferences is not None:
        return load_preferences(db)
    if len(update.assetIds) != len(set(update.assetIds)):
        raise ValueError("Trends selection must not contain duplicate stocks")
    available = {asset_id for (asset_id,) in db.query(WatchlistEntry.alpaca_asset_id)}
    if not set(update.assetIds) <= available:
        raise LookupError("Trends stocks must belong to the watchlist")
    if preferences is None:
        # The singleton key also protects a first import racing with another browser.
        try:
            with db.begin_nested():
                preferences = TrendsPreferences(id=1, asset_ids=update.assetIds, chart_range=update.range)
                db.add(preferences)
                db.flush()
        except IntegrityError:
            preferences = db.get(TrendsPreferences, 1, with_for_update=True)
            if preferences is None:
                raise
            if initialize_only:
                return load_preferences(db)
    preferences.asset_ids = list(update.assetIds)
    preferences.chart_range = update.range
    db.commit()
    return load_preferences(db)
