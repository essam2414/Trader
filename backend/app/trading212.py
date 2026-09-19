"""
Trading212 API client.

This module provides a thin HTTP client wrapper for the Trading212 public API.
It handles HTTP Basic authentication and exposes methods for common operations
like retrieving account summary and positions.
"""

import base64

import httpx

from .rate_limiter import RateLimiter


class Trading212Client:
    """Client for Trading212 API.

    Wraps the Trading212 public API with HTTP Basic authentication.
    Takes api_key and api_secret as constructor arguments for easy testing
    and dependency injection.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        rate_limiter: RateLimiter | None = None,
    ):
        """Initialize the Trading212 client.

        Args:
            api_key: Trading212 API key (username for Basic auth)
            api_secret: Trading212 API secret (password for Basic auth)
            base_url: Base URL for the Trading212 API endpoints
            rate_limiter: Optional shared RateLimiter, acquired before every
                request so this client (and any others sharing the same
                instance) never exceeds Trading212's documented request
                limit. Omit only in tests that don't care about throttling.
        """
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10.0,
        )
        self._rate_limiter = rate_limiter

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> httpx.Response:
        if self._rate_limiter is None:
            response = self._client.get(path, params=params or {})
            response.raise_for_status()
            return response
        with self._rate_limiter:
            response = self._client.get(path, params=params or {})
            response.raise_for_status()
            return response

    def get_account_summary(self) -> dict:
        """Retrieve account summary information.

        Returns:
            Dict containing account details including balance, cash, and investments.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        return self._get("/equity/account/summary").json()

    def get_positions(self) -> list[dict]:
        """Retrieve list of open positions.

        Returns:
            List of dicts, each representing a position with instrument and wallet details.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        return self._get("/equity/positions").json()

    def get_historical_orders(self, cursor: int | None = None, ticker: str | None = None) -> dict:
        """Retrieve one page of historical order/fill data.

        Args:
            cursor: Pagination cursor from a previous page's nextPagePath, or
                None to fetch the first page.
            ticker: Optional ticker to filter results to a single instrument.

        Returns:
            Dict with "items" (list of order/fill records) and "nextPagePath"
            (str or None) for the next page.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        params: dict[str, str | int] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if ticker is not None:
            params["ticker"] = ticker
        return self._get("/equity/history/orders", params).json()

    def get_dividends(self, cursor: int | None = None, ticker: str | None = None) -> dict:
        """Retrieve one page of historical dividend payment data.

        Args:
            cursor: Pagination cursor from a previous page's nextPagePath, or
                None to fetch the first page.
            ticker: Optional ticker to filter results to a single instrument.

        Returns:
            Dict with "items" (list of dividend records) and "nextPagePath"
            (str or None) for the next page.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        params: dict[str, str | int] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if ticker is not None:
            params["ticker"] = ticker
        return self._get("/equity/history/dividends", params).json()
