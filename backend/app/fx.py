"""Historical foreign-exchange rate lookups.

Wraps the Frankfurter API (ECB reference rates - free, no API key, no stated
rate limit) to convert monetary amounts between currencies as of a specific
historical date. Used during history sync to convert Trading212 order fills
that settled in a currency other than the account's base currency (e.g. a
USD-denominated stock trade settled through a USD sub-wallet) into that base
currency, so every stored fill and every metric computed from it is in one
consistent currency.
"""

import httpx

_FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


def get_historical_rate(date: str, from_currency: str, to_currency: str) -> float:
    """Return the from_currency->to_currency exchange rate for the given
    date (YYYY-MM-DD).

    Returns 1.0 without a network call when the currencies match. Frankfurter
    falls back to the nearest earlier business day's published rate for
    weekends/holidays, which is the desired behavior here (a fill on a
    weekend still needs a rate).
    """
    if from_currency == to_currency:
        return 1.0
    response = httpx.get(
        f"{_FRANKFURTER_BASE_URL}/{date}",
        params={"base": from_currency, "symbols": to_currency},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["rates"][to_currency]
