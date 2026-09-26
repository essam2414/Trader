"""OpenAI news cards require source support and stay within the local budget."""

import json
from datetime import date, datetime, timezone

import httpx

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
