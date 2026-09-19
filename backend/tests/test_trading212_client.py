"""Tests for the Trading212Client HTTP wrapper (auth headers, JSON parsing, error handling)."""
import base64

import httpx
import pytest
import respx

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
def test_raises_for_non_200_response():
    """The client should raise HTTPStatusError when Trading212 responds with a non-200 status."""
    respx.get(f"{BASE_URL}/equity/account/summary").mock(return_value=httpx.Response(401))
    client = Trading212Client(api_key="bad", api_secret="bad", base_url=BASE_URL)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.get_account_summary()

    assert exc_info.value.response.status_code == 401
