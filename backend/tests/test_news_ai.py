"""OpenAI news cards require source support and stay within the local budget."""

import json
from datetime import date, datetime, timezone

import httpx
import pytest

from app.config import settings
from app.models import NewsAiDailyUsage, WatchlistEntry
from app.services.news_ai import Evidence, OpenAINewsAnalyser
from app.services.news_ai_budget import DailyNewsTokenBudget
from app.services.news_sources import SourceItem


class FakeBudget:
    def __init__(self):
        self.reserved = []
        self.settled = []

    def reserve(self, estimate):
        self.reserved.append(estimate)
        return date(2026, 9, 25)

    def settle(self, day, estimate, actual):
        self.settled.append((day, estimate, actual))


def _inputs():
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme", exchange="NASDAQ")
    evidence = [
        Evidence(
            4,
            SourceItem(
                "ir_acme",
                "r1",
                "https://example.com/r1",
                "Acme wins contract",
                "Acme announced a supply contract.",
                datetime(2026, 9, 25, tzinfo=timezone.utc),
                ("ACME",),
            ),
        )
    ]
    result = {
        "relevant": True,
        "affectedAssetIds": ["asset-acme"],
        "category": "deal",
        "direction": "upside",
        "headline": "Acme wins contract",
        "shortSummary": "Acme announced a supply contract.",
        "detailSummary": "Acme announced a supply contract.",
        "keyFacts": [],
        "unknowns": [],
        "relevanceReason": "Acme announced a supply contract.",
        "supportingSourceIds": [4],
    }
    return entry, evidence, result


def test_responses_api_uses_strict_card_schema_and_server_side_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, result = _inputs()
    budget = FakeBudget()
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}
                ],
                "usage": {"total_tokens": 123},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    analyser = OpenAINewsAnalyser(budget=budget)
    assert analyser.analyse([entry], evidence) is not None
    url, options = calls[0]
    assert url == "https://api.openai.com/v1/responses"
    assert options["headers"] == {"Authorization": "Bearer test-key"}
    assert options["json"]["model"] == "gpt-5.4-mini"
    assert options["json"]["store"] is False
    assert options["json"]["reasoning"] == {"effort": "none"}
    assert options["json"]["text"]["format"]["strict"] is True
    assert options["json"]["text"]["format"]["schema"]["properties"]["direction"]["enum"] == [
        "upside",
        "downside",
        "unclear",
    ]
    assert budget.settled[0][2] == 123

    result["supportingSourceIds"] = [999]
    assert analyser.analyse([entry], evidence) is None
    result["supportingSourceIds"] = [4]
    result["detailSummary"] = "Acme announced a $10 billion supply contract."
    assert analyser.analyse([entry], evidence) is None


def test_api_error_counts_full_reservation_and_stops_more_calls(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, _ = _inputs()
    budget = FakeBudget()
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return httpx.Response(429, json={"error": "rate limited"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    analyser = OpenAINewsAnalyser(budget=budget)
    assert analyser.analyse([entry], evidence) is None
    assert analyser.analyse([entry], evidence) is None
    assert len(calls) == 1
    assert budget.settled[0][2] is None


def test_fallback_model_omits_unsupported_reasoning_option(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, result = _inputs()
    payloads = []

    def fake_post(url, **kwargs):
        payloads.append(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}
                ],
                "usage": {"total_tokens": 100},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    assert OpenAINewsAnalyser(model="gpt-4.1-mini", budget=FakeBudget()).analyse([entry], evidence)
    assert "reasoning" not in payloads[0]


def test_daily_budget_reserves_before_call_and_persists_usage(db_session):
    def factory():
        return db_session.__class__(bind=db_session.bind)

    budget = DailyNewsTokenBudget(1_000, session_factory=factory)
    day = date(2026, 9, 25)
    assert budget.reserve(700, day) == day
    assert budget.reserve(400, day) is None
    budget.settle(day, 700, 250)
    assert budget.reserve(700, day) == day
    usage = db_session.get(NewsAiDailyUsage, day)
    assert (usage.used_tokens, usage.reserved_tokens, usage.requests) == (250, 700, 2)
    assert DailyNewsTokenBudget(9_000_000, session_factory=factory).limit == 2_500_000


def test_model_receives_every_source_and_full_collected_excerpt(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, result = _inputs()
    evidence = [
        Evidence(
            number,
            SourceItem(
                "publisher",
                str(number),
                f"https://example.com/{number}",
                "Acme wins contract",
                "Acme announced a supply contract. " + "x" * 1700,
                datetime(2026, 9, 25, tzinfo=timezone.utc),
                ("ACME",),
            ),
        )
        for number in range(1, 11)
    ]
    result["supportingSourceIds"] = [10]
    payloads = []

    def fake_post(url, **kwargs):
        payloads.append(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}
                ],
                "usage": {"total_tokens": 500},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    assert OpenAINewsAnalyser(budget=FakeBudget()).analyse([entry], evidence)
    sources = json.loads(payloads[0]["input"])["sources"]
    assert {source["id"] for source in sources} == set(range(1, 11))
    assert all(len(source["excerpt"]) > 1600 for source in sources)


@pytest.mark.parametrize(
    "source,summary,accepted",
    [
        ("Sales $60.000B-$63.000B", "Sales $60B to $63B", True),
        ("Sold 8437 shares at 277.17 per share", "Sold 8,437 shares at $277.17 per share", True),
        ("Sales $60 billion", "Sales $60,000 million", True),
        ("Sales $60B", "Sales $60M", False),
        ("Sales $60B", "Sales EUR60B", False),
        ("Sales $60B", "Sales JPY60B", False),
        ("Filed Form 4", "Sold 4 shares", False),
        ("Growth 10%", "Growth 10", False),
        ("Sales $60B", "Sales $63B", False),
        ("Sales $60 billion-$63 billion", "Sales $60B to $63B", True),
        ("EPS $-5", "EPS $5", False),
        ("Q1 FY28 guidance", "Q2 FY28 guidance", False),
        ("Q1 FY28 guidance", "Q1 FY29 guidance", False),
        ("Second quarter of fiscal year 2027", "Q2 FY27", True),
        ("Growth 10% on 2026-10-06T13:31:57Z", "Growth 10", False),
        ("Released 2026-10-06T13:31:57Z", "Released 2026-10-07", False),
        ("Released 2026-10-06T13:31:57Z", "Released 2026-10-06T13:34:57Z", False),
    ],
)
def test_numeric_validation_preserves_values_currency_and_units(monkeypatch, source, summary, accepted):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, result = _inputs()
    item = evidence[0].item
    evidence = [Evidence(4, SourceItem(item.provider, item.key, item.url, item.title, source, None))]
    result["detailSummary"] = summary
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "status": "completed",
                "usage": {"total_tokens": 100},
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}
                ],
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    analyser = OpenAINewsAnalyser(budget=FakeBudget())
    assert (analyser.analyse([entry], evidence) is not None) == accepted
    assert len(calls) == (1 if accepted else 2)
    if not accepted:
        assert analyser.last_failure_kind == "validation"


def test_numeric_correction_is_bounded_and_uses_original_evidence(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, result = _inputs()
    payloads = []

    def post(url, **kwargs):
        payloads.append(kwargs["json"].copy())
        output = dict(result, detailSummary="Contract worth $99B") if len(payloads) == 1 else result
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "status": "completed",
                "usage": {"total_tokens": 100},
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(output)}]}
                ],
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    budget = FakeBudget()
    assert OpenAINewsAnalyser(budget=budget).analyse([entry], evidence)
    assert len(payloads) == len(budget.settled) == 2
    assert payloads[0]["input"] == payloads[1]["input"]
    assert "unsupported" in payloads[1]["instructions"]


@pytest.mark.parametrize("relevant,accepted", [(True, False), (False, True)])
def test_uncited_numbers_cannot_support_publication_but_irrelevant_articles_can_leave_queue(
    monkeypatch, relevant, accepted
):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    entry, evidence, result = _inputs()
    evidence.append(
        Evidence(
            5,
            SourceItem(
                "publisher",
                "other",
                "https://example.com/other",
                "Other company contract worth $99B",
                "",
                None,
            ),
        )
    )
    result["detailSummary"] = "Contract worth $99B"
    result["relevant"] = relevant
    if not relevant:
        result["affectedAssetIds"] = []
        result["supportingSourceIds"] = []
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}
                ],
            },
        ),
    )
    assert (OpenAINewsAnalyser(budget=FakeBudget()).analyse([entry], evidence) is not None) == accepted
