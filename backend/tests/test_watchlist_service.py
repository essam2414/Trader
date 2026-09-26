"""Persistence rules for the dashboard watchlist."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.alpaca_market_data import AlpacaAsset
from app.config import settings
from app.models import WatchlistEntry
from app.services.watchlist import (
    WatchlistLimitError,
    add_entry,
    get_cached_logo,
    remove_entry,
    reorder_entries,
)


class FakeAlpacaClient:
    def __init__(self):
        self.asset = AlpacaAsset("asset-aapl", "AAPL", "Apple Inc.", "NASDAQ")

    def get_asset(self, asset_id: str):
        return self.asset if asset_id == self.asset.asset_id else None

    def get_company_logo(self, symbol: str):
        assert symbol == self.asset.symbol
        self.logo_requests = getattr(self, "logo_requests", 0) + 1
        return b"png-logo", "image/png"


def test_add_revalidates_asset_and_is_idempotent(db_session):
    client = FakeAlpacaClient()

    first = add_entry(db_session, client, "asset-aapl", limit=2)
    second = add_entry(db_session, client, "asset-aapl", limit=2)

    assert first.id == second.id
    assert db_session.query(WatchlistEntry).count() == 1
    assert first.symbol == "AAPL"


def test_limit_and_remove_are_enforced(db_session):
    client = FakeAlpacaClient()
    add_entry(db_session, client, "asset-aapl", limit=1)
    client.asset = AlpacaAsset("asset-msft", "MSFT", "Microsoft Corp.", "NASDAQ")

    with pytest.raises(WatchlistLimitError):
        add_entry(db_session, client, "asset-msft", limit=1)

    assert remove_entry(db_session, "asset-aapl") is True
    assert remove_entry(db_session, "asset-aapl") is False


def test_default_watchlist_limit_rejects_the_twenty_first_equity(db_session):
    client = FakeAlpacaClient()
    for index in range(settings.alpaca_watchlist_limit):
        client.asset = AlpacaAsset(f"asset-{index}", f"T{index}", f"Test {index}", "NASDAQ")
        add_entry(db_session, client, client.asset.asset_id, limit=settings.alpaca_watchlist_limit)

    client.asset = AlpacaAsset("asset-over-limit", "OVER", "Over Limit", "NASDAQ")
    with pytest.raises(WatchlistLimitError):
        add_entry(db_session, client, client.asset.asset_id, limit=settings.alpaca_watchlist_limit)


def test_database_rejects_duplicate_alpaca_asset_ids(db_session):
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="asset-aapl", symbol="AAPL", name="Apple", exchange="NASDAQ"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_reorder_persists_a_complete_watchlist_order(db_session):
    db_session.add_all(
        [
            WatchlistEntry(
                alpaca_asset_id="asset-aapl",
                symbol="AAPL",
                name="Apple",
                exchange="NASDAQ",
                sort_order=0,
            ),
            WatchlistEntry(
                alpaca_asset_id="asset-msft",
                symbol="MSFT",
                name="Microsoft",
                exchange="NASDAQ",
                sort_order=1,
            ),
        ]
    )
    db_session.commit()

    assert reorder_entries(db_session, ["asset-msft", "asset-aapl"]) is True
    assert [
        entry.alpaca_asset_id
        for entry in db_session.query(WatchlistEntry).order_by(WatchlistEntry.sort_order).all()
    ] == ["asset-msft", "asset-aapl"]
    assert reorder_entries(db_session, ["asset-aapl"]) is False


def test_company_logo_is_cached_in_the_watchlist_entry(db_session):
    client = FakeAlpacaClient()
    entry = add_entry(db_session, client, "asset-aapl", limit=2)

    assert get_cached_logo(db_session, client, entry) == (b"png-logo", "image/png")
    db_session.refresh(entry)
    assert entry.logo_data == b"png-logo"
    assert entry.logo_content_type == "image/png"
    assert entry.logo_provider == "loadlogo"

    assert get_cached_logo(db_session, client, entry) == (b"png-logo", "image/png")
    assert client.logo_requests == 1


def test_new_watchlist_entry_has_its_logo_before_it_is_returned(db_session):
    client = FakeAlpacaClient()

    entry = add_entry(db_session, client, "asset-aapl", limit=2)

    assert entry.logo_data == b"png-logo"
    assert entry.logo_content_type == "image/png"
    assert client.logo_requests == 1


def test_previous_provider_miss_is_retried_for_a_saved_entry(db_session):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-aapl",
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        logo_provider="eulerpool",
        logo_checked_at=datetime.now(timezone.utc),
    )
    db_session.add(entry)
    db_session.commit()

    logo = get_cached_logo(db_session, FakeAlpacaClient(), entry)

    assert logo == (b"png-logo", "image/png")
    assert entry.logo_provider == "loadlogo"


def test_temporary_logo_failure_does_not_prevent_later_retry(db_session):
    class UnavailableLogoClient(FakeAlpacaClient):
        def get_company_logo(self, symbol):
            raise RuntimeError("Provider unavailable")

    entry = add_entry(db_session, UnavailableLogoClient(), "asset-aapl", limit=2)

    assert entry.logo_data is None
    assert entry.logo_checked_at is None
    assert get_cached_logo(db_session, FakeAlpacaClient(), entry) == (b"png-logo", "image/png")
