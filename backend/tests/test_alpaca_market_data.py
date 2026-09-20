"""Tests for Alpaca session, split-adjustment, and stale quote behaviour."""

from datetime import datetime
from decimal import Decimal

import httpx

from app.alpaca_market_data import AlpacaMarketDataClient


def test_after_hours_change_uses_the_session_that_closed_before_the_source_price(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret", feed="iex")
    requests: list[tuple[str, dict[str, str]]] = []

    def fake_request(_base_url: str, path: str, params: dict[str, str]):
        requests.append((path, params))
        if path == "/v2/stocks/snapshots":
            return {"AAPL": {"latestTrade": {"p": 110, "t": "2026-09-18T20:10:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-17", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
            ]
        if params["timeframe"] == "1Day":
            return {"bars": {"AAPL": [{"c": 108}]}}
        return {
            "bars": {
                "AAPL": [
                    {"t": "2026-09-18T12:00:00Z", "c": 104},
                    {"t": "2026-09-18T13:30:00Z", "c": 105},
                ]
            }
        }

    monkeypatch.setattr(client, "_request", fake_request)

    quote = client.get_watchlist_market_data(["AAPL"])["AAPL"]

    assert quote.price == 110
    assert quote.previous_close == 108
    assert quote.dollar_change == 2
    assert quote.percent_change == (Decimal("2") / Decimal("108")) * Decimal("100")
    assert quote.is_extended_hours is True
    assert len(quote.sparkline) == 1
    assert quote.source_timestamp == datetime.fromisoformat("2026-09-18T20:10:00+00:00")
    assert any(params.get("adjustment") == "split" for _, params in requests)


def test_last_successful_quote_is_returned_as_stale_during_an_outage(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")

    def successful_request(_base_url: str, path: str, params: dict[str, str]):
        if path == "/v2/stocks/snapshots":
            return {"MSFT": {"latestTrade": {"p": 100, "t": "2026-09-18T15:00:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-17", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
            ]
        if params["timeframe"] == "1Day":
            return {"bars": {"MSFT": [{"c": 99}]}}
        return {"bars": {"MSFT": [{"t": "2026-09-18T13:30:00Z", "c": 100}]}}

    monkeypatch.setattr(
        client,
        "_request",
        successful_request,
    )
    assert client.get_watchlist_market_data(["MSFT"])["MSFT"].price == 100

    from app.alpaca_market_data import AlpacaUnavailableError

    def unavailable_request(*_args, **_kwargs):
        raise AlpacaUnavailableError()

    monkeypatch.setattr(client, "_request", unavailable_request)
    quote = client.get_watchlist_market_data(["MSFT"])["MSFT"]

    assert quote.price == 100
    assert quote.freshness == "stale"


def test_regular_session_price_uses_prior_close_but_current_session_sparkline(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    monkeypatch.setattr(
        client,
        "_request",
        lambda *_args, **_kwargs: [
            {"date": "2026-09-17", "open": "09:30", "close": "16:00"},
            {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
        ],
    )

    previous_close_session, sparkline_session, is_extended = client._sessions_for_price(
        datetime.fromisoformat("2026-09-18T14:00:00+00:00")
    )

    assert previous_close_session.isoformat() == "2026-09-17"
    assert sparkline_session.isoformat() == "2026-09-18"
    assert is_extended is False


def test_symbol_search_prioritizes_exact_and_prefix_ticker_matches(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    monkeypatch.setattr(
        client,
        "_load_catalog",
        lambda: [
            client_asset("asset-company", "ZZZZ", "AAPL Holdings", "NASDAQ"),
            client_asset("asset-prefix", "AAPLX", "Apple X", "NASDAQ"),
            client_asset("asset-exact", "AAPL", "Apple Inc.", "NASDAQ"),
        ],
    )

    assert [asset.symbol for asset in client.search_us_equities("aapl")] == ["AAPL", "AAPLX", "ZZZZ"]


def test_company_logo_uses_the_ticker_logo_provider_without_credentials(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    request_details = {}

    def fake_get(url, *, headers, timeout):
        request_details.update(url=url, headers=headers, timeout=timeout)
        return httpx.Response(
            200,
            content=b"png-logo",
            headers={"content-type": "image/png; charset=binary"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("app.alpaca_market_data.httpx.get", fake_get)

    assert client.get_company_logo("AAPL") == (b"png-logo", "image/png")
    assert request_details["url"] == "https://api.eulerpool.com/api/1/logo/ticker/AAPL"
    assert request_details["headers"] == {"Accept": "image/*"}


def client_asset(asset_id: str, symbol: str, name: str, exchange: str):
    from app.alpaca_market_data import AlpacaAsset

    return AlpacaAsset(asset_id, symbol, name, exchange)
