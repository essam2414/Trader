"""Semantic decisions must cite actual evidence and share the news token budget."""

import json
from datetime import date

import httpx
import pytest

from app.config import settings
from app.services.news_ai import OpenAINewsAnalyser


class Budget:
    def __init__(self):
        self.settled = []

    def reserve(self, amount):
        return date(2026, 10, 4)

    def settle(self, day, estimate, actual):
        self.settled.append(actual)


@pytest.mark.parametrize(
    "mutation,accepted",
    [
        ({}, True),
        ({"matchedStoryId": 99}, False),
        ({"supportingQuote": "Invented evidence"}, False),
        ({"priorQuote": "Invented prior fact"}, False),
        ({"outcome": "new", "matchedStoryId": None}, True),
        ({"outcome": "new"}, False),
    ],
)
def test_comparison_validates_history_ids_and_both_evidence_quotes(monkeypatch, mutation, accepted):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    result = dict(
        outcome="additional_coverage",
        matchedStoryId=7,
        reason="Same agreement",
        supportingQuote="Micron supplies Acme",
        priorQuote="Acme buys memory from Micron",
    )
    result.update(mutation)
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "status": "completed",
                "usage": {"total_tokens": 80},
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}
                ],
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    budget = Budget()
    analyser = OpenAINewsAnalyser(budget=budget)
    decision = analyser.compare_developments(
        {"evidence": "Micron supplies Acme"}, [{"id": 7, "evidence": "Acme buys memory from Micron"}]
    )
    assert (decision is not None) == accepted
    assert budget.settled == [80]
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["strict"] is True


def test_comparison_rate_limit_defers_later_summary_calls(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_news_enabled", True)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            429, headers={"retry-after": "60"}, request=httpx.Request("POST", url)
        ),
    )
    analyser = OpenAINewsAnalyser(budget=Budget())
    assert analyser.compare_developments({"evidence": "news"}, []) is None
    assert not analyser.available()
