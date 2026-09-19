"""
Trading212 API client.

This module provides a thin HTTP client wrapper for the Trading212 public API.
It handles HTTP Basic authentication and exposes methods for common operations
like retrieving account summary and positions.
"""

import base64

import httpx


class Trading212Client:
    """Client for Trading212 API.

    Wraps the Trading212 public API with HTTP Basic authentication.
    Takes api_key and api_secret as constructor arguments for easy testing
    and dependency injection.
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str):
        """Initialize the Trading212 client.

        Args:
            api_key: Trading212 API key (username for Basic auth)
            api_secret: Trading212 API secret (password for Basic auth)
            base_url: Base URL for the Trading212 API endpoints
        """
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10.0,
        )

    def get_account_summary(self) -> dict:
        """Retrieve account summary information.

        Returns:
            Dict containing account details including balance, cash, and investments.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        response = self._client.get("/equity/account/summary")
        response.raise_for_status()
        return response.json()

    def get_positions(self) -> list[dict]:
        """Retrieve list of open positions.

        Returns:
            List of dicts, each representing a position with instrument and wallet details.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        response = self._client.get("/equity/positions")
        response.raise_for_status()
        return response.json()
