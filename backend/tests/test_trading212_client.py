"""Tests for the Trading212Client HTTP wrapper (auth headers, JSON parsing, error handling)."""

import base64
import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from app.rate_limiter import RateLimiter, Trading212RateLimiter
from app.trading212 import Trading212Client

BASE_URL = "https://live.trading212.com/api/v0"


@respx.mock
def test_get_account_summary_sends_basic_auth_and_returns_json():
    """get_account_summary should send HTTP Basic auth and return the parsed JSON body."""
    route = respx.get(f"{BASE_URL}/equity/account/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 12345,
                "currency": "USD",
                "totalValue": 10250.50,
                "cash": {"availableToTrade": 500.0, "inPies": 0.0, "reservedForOrders": 0.0},
                "investments": {
                    "currentValue": 9750.50,
                    "totalCost": 9000.0,
                    "unrealizedProfitLoss": 750.50,
                    "realizedProfitLoss": 120.0,
                },
            },
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    summary = client.get_account_summary()

    assert route.called
    assert summary["totalValue"] == 10250.50
    expected_auth = "Basic " + base64.b64encode(b"key:secret").decode()
    assert route.calls[0].request.headers["authorization"] == expected_auth


@respx.mock
def test_get_positions_returns_list_of_positions():
    """get_positions should return the parsed list of open position objects."""
    respx.get(f"{BASE_URL}/equity/positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "instrument": {
                        "ticker": "NVDA_US_EQ",
                        "name": "NVIDIA Corp",
                        "isin": "US67066G1040",
                        "currency": "USD",
                    },
                    "quantity": 10.0,
                    "averagePricePaid": 120.5,
                    "currentPrice": 135.2,
                    "quantityAvailableForTrading": 10.0,
                    "quantityInPies": 0.0,
                    "createdAt": "2026-01-15T09:30:00Z",
                    "walletImpact": {
                        "currency": "USD",
                        "currentValue": 1352.0,
                        "fxImpact": 0.0,
                        "totalCost": 1205.0,
                        "unrealizedProfitLoss": 147.0,
                    },
                }
            ],
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    positions = client.get_positions()

    assert len(positions) == 1
    assert positions[0]["instrument"]["ticker"] == "NVDA_US_EQ"


@respx.mock
def test_get_historical_orders_returns_items_and_next_page_path():
    """get_historical_orders should return the parsed page (items + nextPagePath)."""
    respx.get(f"{BASE_URL}/equity/history/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"order": {"id": 1, "ticker": "AAPL_US_EQ"}, "fill": {"id": 101}}],
                "nextPagePath": "/api/v0/equity/history/orders?cursor=2&limit=50",
            },
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    page = client.get_historical_orders()

    assert page["items"][0]["fill"]["id"] == 101
    assert page["nextPagePath"] == "/api/v0/equity/history/orders?cursor=2&limit=50"


@respx.mock
def test_get_historical_orders_sends_cursor_and_max_page_size_as_query_params():
    """When given a cursor, get_historical_orders should send it as a query param."""
    route = respx.get(f"{BASE_URL}/equity/history/orders", params={"cursor": "2", "limit": "50"}).mock(
        return_value=httpx.Response(200, json={"items": [], "nextPagePath": None})
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    client.get_historical_orders(cursor=2)

    assert route.called


@respx.mock
def test_get_historical_orders_omits_cursor_param_on_first_page():
    """With no cursor given, the request should not include a cursor query param at all."""
    respx.get(f"{BASE_URL}/equity/history/orders").mock(
        return_value=httpx.Response(200, json={"items": [], "nextPagePath": None})
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    client.get_historical_orders()

    request = respx.calls[-1].request
    assert "cursor" not in request.url.params


@respx.mock
def test_get_dividends_returns_items_and_next_page_path():
    """get_dividends should return the parsed page (items + nextPagePath)."""
    respx.get(f"{BASE_URL}/equity/history/dividends").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"ticker": "AAPL_US_EQ", "amount": 5.0}],
                "nextPagePath": None,
            },
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    page = client.get_dividends()

    assert page["items"][0]["ticker"] == "AAPL_US_EQ"
    assert page["nextPagePath"] is None


@respx.mock
def test_each_api_call_acquires_the_rate_limiter_when_one_is_provided():
    """Every outgoing call should go through the shared rate limiter first,
    so the client never exceeds Trading212's documented request limit."""
    respx.get(f"{BASE_URL}/equity/account/summary").mock(
        return_value=httpx.Response(
            200, json={"currency": "USD", "totalValue": 0, "cash": {}, "investments": {}}
        )
    )
    respx.get(f"{BASE_URL}/equity/positions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/equity/history/orders").mock(
        return_value=httpx.Response(200, json={"items": [], "nextPagePath": None})
    )
    respx.get(f"{BASE_URL}/equity/history/dividends").mock(
        return_value=httpx.Response(200, json={"items": [], "nextPagePath": None})
    )
    fake_limiter = MagicMock()
    request_limiter = MagicMock()
    request_limiter.__enter__ = MagicMock(return_value=request_limiter)
    request_limiter.__exit__ = MagicMock(return_value=False)
    fake_limiter.limit.return_value = request_limiter
    client = Trading212Client(
        api_key="key", api_secret="secret", base_url=BASE_URL, rate_limiter=fake_limiter
    )

    client.get_account_summary()
    client.get_positions()
    client.get_historical_orders()
    client.get_dividends()

    assert fake_limiter.limit.call_count == 4
    assert [call.args[0] for call in fake_limiter.limit.call_args_list] == [
        "/equity/account/summary",
        "/equity/positions",
        "/equity/history/orders",
        "/equity/history/dividends",
    ]
    assert request_limiter.__enter__.call_count == 4
    assert request_limiter.__exit__.call_count == 4


@respx.mock
def test_shared_rate_limiter_prevents_concurrent_requests_across_threads():
    """A real RateLimiter shared by one client, called from multiple threads at
    once, should never let two HTTP calls to Trading212 overlap - regression
    test for the bug where the limiter released its lock before the request
    fired, letting concurrent callers race and trip Trading212's own
    simultaneous-request rejection."""
    concurrent_count = 0
    max_concurrent = 0
    guard = threading.Lock()

    def slow_response(request):
        nonlocal concurrent_count, max_concurrent
        with guard:
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
        time.sleep(0.05)
        with guard:
            concurrent_count -= 1
        return httpx.Response(200, json={"currency": "USD", "totalValue": 0, "cash": {}, "investments": {}})

    respx.get(f"{BASE_URL}/equity/account/summary").mock(side_effect=slow_response)
    limiter = Trading212RateLimiter({"/equity/account/summary": RateLimiter(max_calls=100, period=60.0)})
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL, rate_limiter=limiter)

    threads = [threading.Thread(target=client.get_account_summary) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent == 1


@respx.mock
def test_raises_for_non_200_response():
    """The client should raise HTTPStatusError when Trading212 responds with a non-200 status."""
    respx.get(f"{BASE_URL}/equity/account/summary").mock(return_value=httpx.Response(401))
    client = Trading212Client(api_key="bad", api_secret="bad", base_url=BASE_URL)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.get_account_summary()

    assert exc_info.value.response.status_code == 401
