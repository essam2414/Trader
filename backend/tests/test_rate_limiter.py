"""Tests for the RateLimiter used to keep Trading212 API calls under its documented limit."""

import threading
import time

from app.rate_limiter import RateLimiter, Trading212RateLimiter


def _fake_clock(start: float = 0.0):
    """Return (time_func, advance) where advance() moves the fake clock forward."""
    state = {"now": start}

    def time_func() -> float:
        return state["now"]

    def advance(seconds: float) -> None:
        state["now"] += seconds

    return time_func, advance


def test_rate_limiter_allows_calls_up_to_the_limit_without_sleeping():
    time_func, _advance = _fake_clock()
    sleeps: list[float] = []
    limiter = RateLimiter(max_calls=6, period=60.0, time_func=time_func, sleep_func=sleeps.append)

    for _ in range(6):
        with limiter:
            pass

    assert sleeps == []


def test_rate_limiter_sleeps_when_the_limit_is_exceeded_within_the_window():
    time_func, advance = _fake_clock()
    sleeps: list[float] = []

    def sleep_func(seconds: float) -> None:
        sleeps.append(seconds)
        advance(seconds)

    limiter = RateLimiter(max_calls=6, period=60.0, time_func=time_func, sleep_func=sleep_func)
    for _ in range(6):
        with limiter:
            pass
    advance(10.0)  # only 10s of the 60s window has passed

    with limiter:
        pass

    assert sleeps == [50.0]  # waits for the oldest call (at t=0) to age out at t=60


def test_rate_limiter_does_not_sleep_once_the_window_has_passed():
    time_func, advance = _fake_clock()
    sleeps: list[float] = []
    limiter = RateLimiter(max_calls=6, period=60.0, time_func=time_func, sleep_func=sleeps.append)

    for _ in range(6):
        with limiter:
            pass
    advance(60.0)  # the whole window has elapsed; all 6 calls should have aged out

    with limiter:
        pass

    assert sleeps == []


def test_rate_limiter_serializes_concurrent_access():
    """Two threads entering the `with limiter:` block should never be inside it
    at the same time — Trading212 rejects genuinely simultaneous requests as
    "too many requests" even within the documented count-based limit, so the
    limiter must hold its lock for the caller's whole critical section, not
    just its own bookkeeping."""
    limiter = RateLimiter(max_calls=100, period=60.0)
    concurrent_count = 0
    max_concurrent = 0
    guard = threading.Lock()

    def worker():
        nonlocal concurrent_count, max_concurrent
        with limiter:
            with guard:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            time.sleep(0.05)
            with guard:
                concurrent_count -= 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent == 1


def test_trading212_limiter_applies_account_summary_limit_independently():
    time_func, advance = _fake_clock()
    sleeps: list[float] = []

    def sleep_func(seconds: float) -> None:
        sleeps.append(seconds)
        advance(seconds)

    limiter = Trading212RateLimiter(
        {
            "/equity/account/summary": RateLimiter(1, 5.0, time_func, sleep_func),
            "/equity/positions": RateLimiter(1, 1.0, time_func, sleep_func),
        }
    )

    with limiter.limit("/equity/account/summary"):
        pass
    with limiter.limit("/equity/positions"):
        pass
    with limiter.limit("/equity/account/summary"):
        pass

    assert sleeps == [5.0]
