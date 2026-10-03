"""Trends selections belong to the database, independently of browser storage."""

import pytest

from app.config import settings
from app.models import WatchlistEntry
from app.services.watchlist import remove_entry

PATH = "/api/watchlist/trends/preferences"
HEADERS = {"Authorization": f"Bearer {settings.dashboard_api_key}"}


@pytest.fixture(autouse=True)
def watched_stocks(db_session):
    db_session.add_all(
        [
            WatchlistEntry(alpaca_asset_id="aapl", symbol="AAPL", name="Apple", exchange="NASDAQ"),
            WatchlistEntry(alpaca_asset_id="msft", symbol="MSFT", name="Microsoft", exchange="NASDAQ"),
        ]
    )
    db_session.commit()


def test_unsaved_layout_has_empty_defaults_without_initializing_it(client):
    response = client.get(PATH, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"assetIds": [], "range": "1W", "initialized": False}


def test_selection_order_and_range_are_shared_across_origins(client, db_session):
    layout = {"assetIds": ["msft", "aapl"], "range": "3M"}
    response = client.put(PATH, headers={**HEADERS, "Origin": "http://localhost:3000"}, json=layout)
    assert response.status_code == 200
    db_session.expire_all()
    loaded = client.get(PATH, headers={**HEADERS, "Origin": "http://localhost:3001"})
    assert loaded.json() == {**layout, "initialized": True}
    assert [(entry.symbol, entry.sort_order) for entry in db_session.query(WatchlistEntry)] == [
        ("AAPL", 0),
        ("MSFT", 0),
    ]


def test_empty_layout_stays_initialized_and_cannot_be_overwritten_by_legacy_import(client):
    assert client.put(PATH, headers=HEADERS, json={"assetIds": [], "range": "1M"}).status_code == 200
    imported = client.put(
        f"{PATH}?initializeOnly=true",
        headers=HEADERS,
        json={"assetIds": ["aapl"], "range": "1W"},
    )
    assert imported.json() == {"assetIds": [], "range": "1M", "initialized": True}


def test_legacy_layout_can_initialize_database_once(client):
    first = client.put(
        f"{PATH}?initializeOnly=true", headers=HEADERS, json={"assetIds": ["msft"], "range": "1Y"}
    )
    assert first.status_code == 200
    second = client.put(
        f"{PATH}?initializeOnly=true", headers=HEADERS, json={"assetIds": ["aapl"], "range": "1W"}
    )
    assert second.json() == first.json()


@pytest.mark.parametrize(
    ("layout", "status"),
    [
        ({"assetIds": ["aapl", "aapl"], "range": "1W"}, 400),
        ({"assetIds": ["missing"], "range": "1W"}, 404),
        ({"assetIds": ["aapl"], "range": "1D"}, 422),
        ({"assetIds": [""], "range": "1W"}, 422),
        ({"assetIds": ["a" * 37], "range": "1W"}, 422),
    ],
)
def test_invalid_update_preserves_saved_layout(client, layout, status):
    saved = {"assetIds": ["msft"], "range": "MAX"}
    assert client.put(PATH, headers=HEADERS, json=saved).status_code == 200
    assert client.put(PATH, headers=HEADERS, json=layout).status_code == status
    assert client.get(PATH, headers=HEADERS).json() == {**saved, "initialized": True}


def test_removing_watchlist_stock_prunes_trends_without_losing_order(client, db_session):
    client.put(PATH, headers=HEADERS, json={"assetIds": ["msft", "aapl"], "range": "3M"})
    assert remove_entry(db_session, "msft")
    assert client.get(PATH, headers=HEADERS).json() == {
        "assetIds": ["aapl"],
        "range": "3M",
        "initialized": True,
    }
    db_session.add(WatchlistEntry(alpaca_asset_id="msft", symbol="MSFT", name="Microsoft", exchange="NASDAQ"))
    db_session.commit()
    assert client.get(PATH, headers=HEADERS).json()["assetIds"] == ["aapl"]


def test_preferences_require_authentication(client):
    assert client.get(PATH).status_code == 401
    assert client.put(PATH, json={"assetIds": [], "range": "1W"}).status_code == 401
