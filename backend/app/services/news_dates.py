"""One publication-time policy for ingestion, reconciliation and repair."""

from collections.abc import Iterable
from datetime import datetime, timezone

from ..models import NewsSourceItem


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def better_release_date(
    candidate: datetime,
    candidate_precision: str | None,
    current: datetime | None,
    current_precision: str | None,
) -> bool:
    if current is None:
        return True
    candidate, current = utc(candidate), utc(current)
    if candidate.date() != current.date():
        return candidate < current
    if (candidate_precision == "date") != (current_precision == "date"):
        return candidate_precision != "date"
    return candidate < current


def earliest_release(sources: Iterable[NewsSourceItem]) -> NewsSourceItem | None:
    chosen = None
    for source in sources:
        if source.published_at and (
            chosen is None
            or better_release_date(
                source.published_at,
                source.published_date_precision,
                chosen.published_at,
                chosen.published_date_precision,
            )
        ):
            chosen = source
    return chosen
