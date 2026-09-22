"""Extended-hours source selection for the watchlist."""

from datetime import datetime, timezone

from app.alpaca_market_data import MarketSessionStatus
from app.watchlist_price_resolver import WatchlistPriceResolver


def session(phase: str) -> MarketSessionStatus:
    return MarketSessionStatus(phase, datetime(2026, 9, 22, tzinfo=timezone.utc), None, None, None, False)


def test_pre_market_uses_delayed_sip_before_iex_opens():
    now = datetime(2026, 9, 22, 11, 59, tzinfo=timezone.utc)  # 07:59 New York

    assert WatchlistPriceResolver.select_feed(session("pre_market"), now, now) == "delayed_sip"


def test_pre_market_uses_iex_after_its_open_when_the_symbol_is_fresh():
    now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)  # 08:00 New York

    assert WatchlistPriceResolver.select_feed(session("pre_market"), now, now) == "iex"


def test_iex_silent_extended_hours_symbol_falls_back_to_delayed_sip():
    now = datetime(2026, 9, 22, 20, 30, tzinfo=timezone.utc)  # 16:30 New York
    stale_iex = datetime(2026, 9, 22, 20, 20, tzinfo=timezone.utc)

    assert WatchlistPriceResolver.select_feed(session("after_hours"), now, stale_iex) == "delayed_sip"


def test_after_hours_uses_delayed_sip_once_iex_has_closed():
    now = datetime(2026, 9, 22, 21, tzinfo=timezone.utc)  # 17:00 New York

    assert WatchlistPriceResolver.select_feed(session("after_hours"), now, now) == "delayed_sip"


def test_regular_hours_stay_on_iex_and_overnight_has_no_live_source():
    now = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)

    assert WatchlistPriceResolver.select_feed(session("regular"), now, None) == "iex"
    assert WatchlistPriceResolver.select_feed(session("overnight"), now, now) is None


def test_delayed_sip_is_fresh_for_its_expected_fifteen_minute_lag():
    now = datetime(2026, 9, 22, 21, tzinfo=timezone.utc)
    delayed_trade = datetime(2026, 9, 22, 20, 45, tzinfo=timezone.utc)

    assert WatchlistPriceResolver.is_delayed_sip_current(delayed_trade, now)
