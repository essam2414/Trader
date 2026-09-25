"""Tests for Alpaca session, split-adjustment, and stale quote behaviour."""

from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from app.alpaca_market_data import AlpacaMarketDataClient


@pytest.mark.parametrize(
    ("current_price", "expected_change", "expected_percent"),
    [
        (Decimal("140.25"), Decimal("3.25"), (Decimal("3.25") / Decimal("137")) * Decimal("100")),
        (Decimal("134.86"), Decimal("-2.14"), (Decimal("-2.14") / Decimal("137")) * Decimal("100")),
        (Decimal("137"), Decimal("0"), Decimal("0")),
    ],
)
def test_daily_change_uses_prior_trading_close_for_positive_negative_and_zero(
    monkeypatch, current_price, expected_change, expected_percent
):
    client = AlpacaMarketDataClient("key", "secret", feed="iex")

    def fake_request(_base_url: str, path: str, params: dict[str, str]):
        if path == "/v2/stocks/snapshots":
            return {"AAPL": {"latestTrade": {"p": str(current_price), "t": "2026-09-18T14:00:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-17", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
            ]
        if params["timeframe"] == "1Day":
            assert params["start"] == "2026-09-17T00:00:00+00:00"
            assert params["adjustment"] == "raw"
            return {"bars": {"AAPL": [{"c": "137"}]}}
        return {"bars": {"AAPL": []}}

    monkeypatch.setattr(client, "_request", fake_request)
    quote = client.get_watchlist_market_data(
        ["AAPL"], now=datetime.fromisoformat("2026-09-18T14:00:00+00:00")
    )["AAPL"]

    assert quote.previous_close == Decimal("137")
    assert quote.dollar_change == expected_change
    assert quote.percent_change == expected_percent


def test_monday_daily_change_uses_friday_final_close(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret", feed="iex")

    def fake_request(_base_url: str, path: str, params: dict[str, str]):
        if path == "/v2/stocks/snapshots":
            return {"AAPL": {"latestTrade": {"p": "140.25", "t": "2026-09-21T14:00:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-21", "open": "09:30", "close": "16:00"},
            ]
        if params["timeframe"] == "1Day":
            assert params["start"] == "2026-09-18T00:00:00+00:00"
            return {"bars": {"AAPL": [{"c": "137"}]}}
        return {"bars": {"AAPL": []}}

    monkeypatch.setattr(client, "_request", fake_request)
    quote = client.get_watchlist_market_data(
        ["AAPL"], now=datetime.fromisoformat("2026-09-21T14:00:00+00:00")
    )["AAPL"]

    assert quote.previous_close == Decimal("137")
    assert quote.dollar_change == Decimal("3.25")


def test_holiday_daily_change_skips_the_non_trading_day(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret", feed="iex")

    def fake_request(_base_url: str, path: str, params: dict[str, str]):
        if path == "/v2/stocks/snapshots":
            return {"AAPL": {"latestTrade": {"p": "140.25", "t": "2026-09-08T14:00:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-04", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-08", "open": "09:30", "close": "16:00"},
            ]
        if params["timeframe"] == "1Day":
            assert params["start"] == "2026-09-04T00:00:00+00:00"
            return {"bars": {"AAPL": [{"c": "137"}]}}
        return {"bars": {"AAPL": []}}

    monkeypatch.setattr(client, "_request", fake_request)
    quote = client.get_watchlist_market_data(
        ["AAPL"], now=datetime.fromisoformat("2026-09-08T14:00:00+00:00")
    )["AAPL"]

    assert quote.previous_close == Decimal("137")
    assert quote.dollar_change == Decimal("3.25")


def test_daily_change_requests_only_the_prior_session_official_close(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret", feed="iex")

    def fake_request(_base_url: str, path: str, params: dict[str, str]):
        if path == "/v2/stocks/snapshots":
            return {"AAPL": {"latestTrade": {"p": "140.25", "t": "2026-09-23T14:00:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-22", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-23", "open": "09:30", "close": "16:00"},
            ]
        if params["timeframe"] == "1Day":
            assert params == {
                "symbols": "AAPL",
                "timeframe": "1Day",
                "start": "2026-09-22T00:00:00+00:00",
                "end": "2026-09-23T00:00:00+00:00",
                "adjustment": "raw",
                "feed": "sip",
            }
            return {"bars": {"AAPL": [{"c": "137"}]}}
        return {"bars": {"AAPL": []}}

    monkeypatch.setattr(client, "_request", fake_request)
    quote = client.get_watchlist_market_data(
        ["AAPL"], now=datetime.fromisoformat("2026-09-23T14:00:00+00:00")
    )["AAPL"]

    assert quote.previous_close == Decimal("137")
    assert quote.percent_change == (Decimal("3.25") / Decimal("137")) * Decimal("100")


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

    quote = client.get_watchlist_market_data(
        ["AAPL"], now=datetime.fromisoformat("2026-09-18T20:10:00+00:00")
    )["AAPL"]

    assert quote.price == 110
    assert quote.previous_close == 108
    assert quote.dollar_change == 2
    assert quote.percent_change == (Decimal("2") / Decimal("108")) * Decimal("100")
    assert quote.is_extended_hours is True
    assert [(point.timestamp.isoformat(), point.close) for point in quote.sparkline] == [
        ("2026-09-18T12:00:00+00:00", Decimal("104")),
        ("2026-09-18T13:30:00+00:00", Decimal("105")),
        ("2026-09-18T20:00:00+00:00", Decimal("110")),
    ]
    assert quote.source_timestamp == datetime.fromisoformat("2026-09-18T20:10:00+00:00")
    previous_close_request = next(params for _, params in requests if params.get("timeframe") == "1Day")
    assert previous_close_request["start"] == "2026-09-17T00:00:00+00:00"
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


def test_watchlist_sparkline_uses_15_minute_bars_from_the_preceding_24_hours(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    requests: list[dict[str, str]] = []

    def fake_request(_base_url: str, path: str, params: dict[str, str]):
        if path == "/v2/stocks/snapshots":
            return {"AAPL": {"latestTrade": {"p": 110, "t": "2026-09-18T14:07:00Z"}}}
        if path == "/v2/calendar":
            return [
                {"date": "2026-09-17", "open": "09:30", "close": "16:00"},
                {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
            ]
        requests.append(params)
        if params["timeframe"] == "1Day":
            return {"bars": {"AAPL": [{"c": 108}]}}
        return {
            "bars": {
                "AAPL": [
                    {"t": "2026-09-17T14:00:00Z", "c": 99},
                    {"t": "2026-09-17T14:15:00Z", "c": 100},
                    {"t": "2026-09-18T14:00:00Z", "c": 109},
                    {"t": "2026-09-18T14:15:00Z", "c": 111},
                ]
            }
        }

    monkeypatch.setattr(client, "_request", fake_request)
    quote = client.get_watchlist_market_data(
        ["AAPL"], now=datetime.fromisoformat("2026-09-18T14:07:00+00:00")
    )["AAPL"]

    sparkline_request = next(params for params in requests if params["timeframe"] == "15Min")
    assert sparkline_request == {
        "symbols": "AAPL",
        "timeframe": "15Min",
        "start": "2026-09-17T14:07:00+00:00",
        "end": "2026-09-18T14:07:00+00:00",
        "adjustment": "split",
        "feed": "iex",
        "limit": "10000",
        "sort": "asc",
    }
    assert [(point.timestamp.isoformat(), point.close) for point in quote.sparkline] == [
        ("2026-09-17T14:15:00+00:00", Decimal("100")),
        ("2026-09-18T14:00:00+00:00", Decimal("110")),
    ]


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


def test_company_logo_resolves_ticker_and_fetches_image_without_credentials(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")
    requests = []

    def fake_get(url, *, headers, timeout):
        requests.append((url, headers))
        if url == "https://api.loadlogo.com/ticker/AAPL":
            return httpx.Response(
                200,
                json={"symbol": "AAPL", "domain": "apple.com"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200,
            content=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            headers={"content-type": "image/svg+xml"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("app.alpaca_market_data.httpx.get", fake_get)

    assert client.get_company_logo("AAPL") == (
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        "image/svg+xml",
    )
    assert requests == [
        ("https://api.loadlogo.com/ticker/AAPL", {"Accept": "application/json"}),
        ("https://img.loadlogo.com/apple.com", {"Accept": "image/*"}),
    ]


def test_company_logo_rejects_unsafe_provider_domain(monkeypatch):
    client = AlpacaMarketDataClient("key", "secret")

    def fake_get(url, *, headers, timeout):
        assert url == "https://api.loadlogo.com/ticker/AAPL"
        return httpx.Response(
            200,
            json={"symbol": "AAPL", "domain": "localhost"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("app.alpaca_market_data.httpx.get", fake_get)

    assert client.get_company_logo("AAPL") is None


def client_asset(asset_id: str, symbol: str, name: str, exchange: str):
    from app.alpaca_market_data import AlpacaAsset

    return AlpacaAsset(asset_id, symbol, name, exchange)
