"""Select the best available read-only watchlist price source by US session."""

from __future__ import annotations

from datetime import datetime, timedelta
from datetime import time as clock_time
from typing import Literal

from .alpaca_market_data import NEW_YORK, MarketSessionStatus

PriceFeed = Literal["iex", "delayed_sip"]

IEX_PRE_MARKET_OPEN = clock_time(8, 0)
IEX_POST_MARKET_CLOSE = clock_time(17, 0)
DELAYED_SIP_FRESHNESS = timedelta(minutes=20)


class WatchlistPriceResolver:
    """Hide session and freshness policy behind one source-selection interface.

    IEX remains the source throughout its scheduled pre-market and post-market
    windows. Delayed SIP fills only the portions of extended trading where IEX
    does not operate.
    """

    @staticmethod
    def select_feed(
        session: MarketSessionStatus,
        now: datetime,
        _iex_timestamp: datetime | None,
    ) -> PriceFeed | None:
        return WatchlistPriceResolver.preferred_feed(session, now)

    @staticmethod
    def preferred_feed(session: MarketSessionStatus, now: datetime) -> PriceFeed | None:
        """Return the scheduled source for the current market phase."""
        local_now = now.astimezone(NEW_YORK)
        if session.phase == "regular":
            return "iex"
        if session.phase == "pre_market":
            return "iex" if local_now.timetz().replace(tzinfo=None) >= IEX_PRE_MARKET_OPEN else "delayed_sip"
        if session.phase == "after_hours":
            return "iex" if local_now.timetz().replace(tzinfo=None) < IEX_POST_MARKET_CLOSE else "delayed_sip"
        return None

    @staticmethod
    def is_delayed_sip_current(timestamp: datetime | None, now: datetime) -> bool:
        """A delayed trade is current when it is within its expected delayed window."""
        if timestamp is None:
            return False
        age = now - timestamp
        return timedelta(0) <= age <= DELAYED_SIP_FRESHNESS
