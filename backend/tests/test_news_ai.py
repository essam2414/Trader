"""Reject unsupported local-model outputs before publishing a card."""

import json
from datetime import datetime, timezone

import httpx

from app.models import WatchlistEntry
from app.services.news_ai import Evidence, LocalNewsAnalyser
from app.services.news_sources import SourceItem


def test_model_rejects_unknown_ids_and_fabricated_numbers(monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme", exchange="NASDAQ")
    evidence = [
        Evidence(
            4,
            SourceItem(
                "company",
                "r1",
                "https://example.com/r1",
                "Acme wins contract",
                "Acme announced a supply contract.",
                datetime.now(timezone.utc),
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
        "relevanceReason": "Acme is watched.",
        "supportingSourceIds": [4],
    }

    def fake_post(_url, **_kwargs):
        response = httpx.Response(200, json={"message": {"content": json.dumps(result)}})
        response.request = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    analyser = LocalNewsAnalyser()
    assert analyser.analyse([entry], evidence) is not None

    result["supportingSourceIds"] = [999]
    assert analyser.analyse([entry], evidence) is None
    result["supportingSourceIds"] = [4]
    result["detailSummary"] = "Acme announced a $10 billion supply contract."
    assert analyser.analyse([entry], evidence) is None


def test_old_ollama_schema_error_falls_back_to_json_and_still_validates(monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme", exchange="NASDAQ")
    evidence = [
        Evidence(
            4,
            SourceItem(
                "company",
                "r1",
                "https://example.com/r1",
                "Acme wins contract",
                "Acme announced a supply contract.",
                datetime.now(timezone.utc),
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
        "relevanceReason": "Acme is watched.",
        "supportingSourceIds": [4],
    }
    calls = []

    def fake_post(_url, **kwargs):
        calls.append(kwargs["json"])
        request = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
        if len(calls) == 1:
            return httpx.Response(
                500, json={"error": "failed to load model vocabulary required for format"}, request=request
            )
        return httpx.Response(200, json={"message": {"content": json.dumps(result)}}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert LocalNewsAnalyser().analyse([entry], evidence) is not None
    assert len(calls) == 2
    assert calls[1]["format"] == "json"
