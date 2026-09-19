"""Tests for the historical FX rate lookup used during history sync."""

import httpx
import respx

from app.fx import get_historical_rate

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


def test_get_historical_rate_returns_1_for_same_currency_without_a_network_call():
    assert get_historical_rate("2026-01-09", "GBP", "GBP") == 1.0


@respx.mock
def test_get_historical_rate_fetches_and_parses_the_rate():
    respx.get(f"{FRANKFURTER_BASE_URL}/2026-01-09", params={"base": "USD", "symbols": "GBP"}).mock(
        return_value=httpx.Response(
            200, json={"amount": 1.0, "base": "USD", "date": "2026-01-09", "rates": {"GBP": 0.74532}}
        )
    )

    rate = get_historical_rate("2026-01-09", "USD", "GBP")

    assert rate == 0.74532
