"""Bounded web discovery for watched companies using cited OpenAI search results."""

import re
from datetime import date, datetime

import httpx
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..models import WatchlistEntry
from .news_ai_budget import DailyNewsTokenBudget
from .news_sources import NewsHttp, SourceItem, canonical_url, company_match, source_key

SEARCH_MAX_OUTPUT_TOKENS = 25_000
SEARCH_RETRY_MAX_OUTPUT_TOKENS = 40_000
# Covers the retry output ceiling plus the prompt and web-search context.
SEARCH_TOKEN_RESERVATION = 64_000
NUMBERED_HEADING = re.compile(r"(?m)^\s*\d+\.\s+\*\*(?P<heading>[^*]{10,300})\*\*")
PRICE_MOVE_HEADING = re.compile(
    r"\b(?:stock|shares)\b.{0,45}\b(?:surg\w*|jump\w*|rall\w*|ris\w*|fell|dropp\w*)\b",
    re.I,
)


def _cited_heading(text: str, citation_start: object) -> str:
    """Use the claim attached to a citation, never an uncited model sentence."""
    if not isinstance(citation_start, int) or citation_start < 0:
        return ""
    preceding = [match for match in NUMBERED_HEADING.finditer(text[:citation_start])]
    if not preceding or citation_start - preceding[-1].end() > 800:
        return ""
    return preceding[-1].group("heading").strip()


class OpenAIWebNewsDiscovery:
    """Discover publisher URLs; article titles, not model prose, become source evidence."""

    def __init__(self) -> None:
        self.budget = DailyNewsTokenBudget(settings.openai_news_daily_token_budget)

    def available(self) -> bool:
        return bool(
            settings.openai_news_web_search_enabled
            and settings.openai_news_enabled
            and settings.openai_api_key
        )

    def _reserve(self) -> date | None:
        return self.budget.reserve(SEARCH_TOKEN_RESERVATION)

    def _settle(self, day: date, actual: int | None) -> None:
        self.budget.settle(day, SEARCH_TOKEN_RESERVATION, actual)

    def _reserve_or_error(self) -> date | None:
        try:
            return self._reserve()
        except SQLAlchemyError as exc:
            raise ValueError("OpenAI news token budget store unavailable") from exc

    def _settle_safely(self, day: date, actual: int | None) -> None:
        try:
            self._settle(day, actual)
        except SQLAlchemyError:
            # Keep the reservation when usage could not be settled.
            pass

    def _request(self, payload: dict) -> dict:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
            timeout=75,
        )
        response.raise_for_status()
        return response.json()

    def search(
        self, entry: WatchlistEntry, since: datetime, until: datetime, http: NewsHttp | None = None
    ) -> list[SourceItem]:
        if not self.available():
            return []
        day = self._reserve_or_error()
        if day is None:
            raise ValueError("OpenAI daily news token budget exhausted before web search")
        payload = {
            "model": settings.openai_news_model,
            "tools": [{"type": "web_search", "search_context_size": "low"}],
            "tool_choice": "required",
            "max_tool_calls": 1,
            "max_output_tokens": SEARCH_MAX_OUTPUT_TOKENS,
            "reasoning": {"effort": "low"},
            "store": False,
            "instructions": (
                "Search the live web for material company-specific stock news, including analyst "
                "initiations, rating changes, price targets, earnings, guidance, filings, deals and "
                "regulatory decisions. Give up to five developments with direct, clickable citations "
                "to publisher articles. Prefer original reports. Do not invent dates or facts. "
                "Do not include routine stock-price commentary without an underlying catalyst."
                " Format each development as a numbered item with one bold factual headline, "
                "followed by its citation."
            ),
            "input": (
                f"Find significant news for {entry.name} (NASDAQ/NYSE ticker {entry.symbol}) "
                f"published from {since.date().isoformat()} through {until.date().isoformat()} "
                "inclusive. Search for analyst coverage and target changes as well as company news."
            ),
        }
        actual: int | None = None
        first_settled = False
        try:
            body = self._request(payload)
            usage = body.get("usage") or {}
            if isinstance(usage.get("total_tokens"), int):
                actual = usage["total_tokens"]
            if (
                body.get("status") == "incomplete"
                and (body.get("incomplete_details") or {}).get("reason") == "max_output_tokens"
            ):
                self._settle_safely(day, actual)
                first_settled = True
                retry_day = self._reserve_or_error()
                if retry_day is not None:
                    retry_actual: int | None = None
                    try:
                        retry_payload = {**payload, "max_output_tokens": SEARCH_RETRY_MAX_OUTPUT_TOKENS}
                        body = self._request(retry_payload)
                        retry_usage = body.get("usage") or {}
                        if isinstance(retry_usage.get("total_tokens"), int):
                            retry_actual = retry_usage["total_tokens"]
                    finally:
                        self._settle_safely(retry_day, retry_actual)
            if body.get("status") != "completed":
                reason = str((body.get("incomplete_details") or {}).get("reason") or "unknown")
                reason = re.sub(r"[^a-z_]+", "_", reason.lower())[:48]
                raise ValueError(f"OpenAI web search {body.get('status')}: {reason}")
            if not any(item.get("type") == "web_search_call" for item in body.get("output", [])):
                raise ValueError("OpenAI response did not perform a web search")
            items: list[SourceItem] = []
            seen: set[str] = set()
            seen_headings: set[str] = set()
            for output in body.get("output", []):
                if output.get("type") != "message":
                    continue
                for part in output.get("content", []):
                    model_text = str(part.get("text") or "")
                    for citation in part.get("annotations", []):
                        if citation.get("type") != "url_citation":
                            continue
                        url = canonical_url(str(citation.get("url") or ""))
                        title = str(citation.get("title") or "").strip()[:500]
                        heading = _cited_heading(model_text, citation.get("start_index"))
                        if (
                            not url
                            or url in seen
                            or not title
                            or not heading
                            or heading.lower() in seen_headings
                            or PRICE_MOVE_HEADING.search(heading)
                        ):
                            continue
                        date_status = "unverified"
                        published_date_precision = "minute"
                        event_date = None
                        if http is not None and hasattr(http, "article_metadata_result"):
                            metadata = http.article_metadata_result(url)
                            excerpt, published = metadata.description, metadata.published_at
                            date_status = metadata.status
                            published_date_precision = metadata.date_precision or "minute"
                            event_date = metadata.event_date
                        elif http is not None:
                            excerpt, published = http.article_metadata(url)
                        else:
                            excerpt, published = "", None
                        if not company_match(f"{title} {excerpt}", entry):
                            continue
                        if published is not None and not since <= published <= until:
                            continue
                        seen.add(url)
                        seen_headings.add(heading.lower())
                        # The search model's heading locates a lead; it is not publisher
                        # evidence for the later summariser.
                        items.append(
                            SourceItem(
                                "openai_web",
                                source_key("openai_web", url),
                                url,
                                title,
                                excerpt[:1200],
                                published,
                                date_status=date_status,
                                published_date_precision=published_date_precision,
                                event_date=event_date,
                            )
                        )
            return items[:5]
        finally:
            if not first_settled:
                self._settle_safely(day, actual)
