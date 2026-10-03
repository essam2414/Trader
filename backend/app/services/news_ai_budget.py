"""Persistent UTC-day cap for this app's OpenAI news traffic."""

from datetime import date, datetime, timezone
from threading import Lock
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import NewsAiDailyUsage

_reservation_lock = Lock()


class DailyNewsTokenBudget:
    def __init__(
        self,
        limit: int,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        # OpenAI's data-sharing counter resets at 00:00 UTC; default leaves 100k headroom.
        self.limit = max(0, min(limit, 2_500_000))
        self.session_factory = session_factory

    def reserve(self, estimate: int, day: date | None = None) -> date | None:
        if estimate <= 0 or estimate > self.limit:
            return None
        day = day or datetime.now(timezone.utc).date()
        with _reservation_lock, self.session_factory() as db, db.begin():
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(20260925)"))
            usage = db.get(NewsAiDailyUsage, day)
            if usage is None:
                usage = NewsAiDailyUsage(day=day, reserved_tokens=0, used_tokens=0, requests=0)
                db.add(usage)
                db.flush()
            if usage.used_tokens + usage.reserved_tokens + estimate > self.limit:
                return None
            usage.reserved_tokens += estimate
            usage.requests += 1
        return day

    def settle(self, day: date, estimate: int, actual: int | None) -> None:
        # Unknown usage counts at the full reservation, including ambiguous timeouts.
        charged = estimate if actual is None else max(0, actual)
        with _reservation_lock, self.session_factory() as db, db.begin():
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(20260925)"))
            usage = db.get(NewsAiDailyUsage, day)
            if usage is None:
                return
            usage.reserved_tokens = max(0, usage.reserved_tokens - estimate)
            usage.used_tokens += charged
