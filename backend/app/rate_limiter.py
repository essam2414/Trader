"""Sliding-window rate limiter, used to keep calls to the Trading212 API
under its documented request limit (6 requests per 60 seconds). Trading212
also rejects genuinely *simultaneous* requests outright ("too many
requests") independent of that count, so this limiter is a full
serialization gate: `with limiter:` holds its lock for the caller's whole
critical section (the HTTP call), not just its own bookkeeping, so two
threads can never have a Trading212 request in flight at the same time.

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


trading212_rate_limiter = RateLimiter(max_calls=6, period=60.0)
