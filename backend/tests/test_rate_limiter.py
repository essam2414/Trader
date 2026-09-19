"""Tests for the RateLimiter used to keep Trading212 API calls under its documented limit."""

from app.rate_limiter import RateLimiter


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
        limiter.acquire()

    assert sleeps == []


def test_rate_limiter_sleeps_when_the_limit_is_exceeded_within_the_window():
    time_func, advance = _fake_clock()
    sleeps: list[float] = []

    def sleep_func(seconds: float) -> None:
        sleeps.append(seconds)
        advance(seconds)

    limiter = RateLimiter(max_calls=6, period=60.0, time_func=time_func, sleep_func=sleep_func)
    for _ in range(6):
        limiter.acquire()
    advance(10.0)  # only 10s of the 60s window has passed

    limiter.acquire()

    assert sleeps == [50.0]  # waits for the oldest call (at t=0) to age out at t=60


def test_rate_limiter_does_not_sleep_once_the_window_has_passed():
    time_func, advance = _fake_clock()
    sleeps: list[float] = []
    limiter = RateLimiter(max_calls=6, period=60.0, time_func=time_func, sleep_func=sleeps.append)

    for _ in range(6):
        limiter.acquire()
    advance(60.0)  # the whole window has elapsed; all 6 calls should have aged out

    limiter.acquire()

    assert sleeps == []
