"""Short-lived cache for the live Trading212 portfolio response.

The Trading212 account-summary endpoint permits one request every five
seconds. Reusing a successful response for that window prevents page
navigations and refreshes from queueing behind the provider's limit.
"""

import threading
import time
from collections.abc import Callable

from ..schemas import PortfolioCurrent


class PortfolioCurrentCache:
    """Keep one successful live portfolio response for a small freshness window."""

    def __init__(
        self,
        ttl_seconds: float = 5.0,
        time_func: Callable[[], float] = time.monotonic,
    ):
        self._ttl_seconds = ttl_seconds
        self._time = time_func
        self._value: PortfolioCurrent | None = None
        self._loaded_at: float | None = None
        self._loading = False
        self._condition = threading.Condition()

    def get(self, load: Callable[[], PortfolioCurrent]) -> PortfolioCurrent:
        """Return a fresh cached value, sharing one in-flight provider request."""
        with self._condition:
            if self._is_fresh():
                return self._value

            while self._loading:
                self._condition.wait()
                if self._is_fresh():
                    return self._value

            self._loading = True

        try:
            value = load()
        except Exception:
            with self._condition:
                self._loading = False
                self._condition.notify_all()
            raise

        with self._condition:
            self._value = value
            self._loaded_at = self._time()
            self._loading = False
            self._condition.notify_all()
            return value

    def _is_fresh(self) -> bool:
        return (
            self._value is not None
            and self._loaded_at is not None
            and self._time() - self._loaded_at < self._ttl_seconds
        )
