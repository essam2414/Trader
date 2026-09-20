"""Trading212 request throttling.

Trading212 publishes separate quotas per endpoint. A shared
``Trading212RateLimiter`` keeps those budgets independent while serializing
all in-flight requests, because the API rejects genuinely simultaneous calls.
It is shared by the live client and every scheduler client, so all code paths
coordinate against the same per-endpoint allowance.
"""

import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Callable


class RateLimiter:
    """A context manager: `with limiter:` blocks until making another call
    would stay within `max_calls` calls per rolling `period`-second window,
    then holds its lock until the block exits — serializing every caller
    against every other, across threads."""

    def __init__(
        self,
        max_calls: int,
        period: float,
        time_func: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], None] = time.sleep,
    ):
        self._max_calls = max_calls
        self._period = period
        self._time = time_func
        self._sleep = sleep_func
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def __enter__(self) -> "RateLimiter":
        self._lock.acquire()
        self._evict_expired()
        if len(self._calls) >= self._max_calls:
            wait = self._period - (self._time() - self._calls[0])
            if wait > 0:
                self._sleep(wait)
            self._evict_expired()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._calls.append(self._time())
        self._lock.release()

    def _evict_expired(self) -> None:
        now = self._time()
        while self._calls and now - self._calls[0] >= self._period:
            self._calls.popleft()


class Trading212RateLimiter:
    """Apply Trading212's documented limits independently per endpoint.

    Requests remain globally serialized because Trading212 rejects simultaneous
    requests. That serialization does not merge the endpoints' separate rate
    budgets: a positions request does not consume an account-summary request.
    """

    def __init__(self, endpoint_limiters: dict[str, RateLimiter] | None = None):
        self._endpoint_limiters = endpoint_limiters or {
            "/equity/account/summary": RateLimiter(max_calls=1, period=5.0),
            "/equity/positions": RateLimiter(max_calls=1, period=1.0),
            "/equity/history/orders": RateLimiter(max_calls=6, period=60.0),
            "/equity/history/dividends": RateLimiter(max_calls=6, period=60.0),
        }
        self._request_lock = threading.Lock()

    @contextmanager
    def limit(self, path: str) -> Iterator[None]:
        """Reserve the rate budget for ``path`` and serialize its request."""
        try:
            endpoint_limiter = self._endpoint_limiters[path]
        except KeyError as exc:
            raise ValueError(f"No Trading212 rate limit configured for {path}") from exc

        with self._request_lock:
            with endpoint_limiter:
                yield


trading212_rate_limiter = Trading212RateLimiter()
