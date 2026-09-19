"""Sliding-window rate limiter, used to keep calls to the Trading212 API
under its documented request limit (6 requests per 60 seconds, observed to
apply account-wide rather than per-endpoint).

A single shared `trading212_rate_limiter` instance is used everywhere a
Trading212Client is constructed (the live shared client in `main.py`'s
lifespan, and each fresh client the scheduler builds per job run), so every
code path that calls the Trading212 API coordinates against the same budget.
"""

import threading
import time
from collections import deque
from typing import Callable


class RateLimiter:
    """Blocks the caller as needed so no more than `max_calls` calls happen
    within any rolling `period`-second window. Thread-safe, since the shared
    instance may be used from FastAPI request handlers and the background
    scheduler at the same time."""

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

    def acquire(self) -> None:
        """Block until making another call would stay within the limit, then
        record this call."""
        with self._lock:
            self._evict_expired()
            if len(self._calls) >= self._max_calls:
                wait = self._period - (self._time() - self._calls[0])
                if wait > 0:
                    self._sleep(wait)
                self._evict_expired()
            self._calls.append(self._time())

    def _evict_expired(self) -> None:
        now = self._time()
        while self._calls and now - self._calls[0] >= self._period:
            self._calls.popleft()


trading212_rate_limiter = RateLimiter(max_calls=6, period=60.0)
