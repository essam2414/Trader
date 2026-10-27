"""Search discovery only admits cited, matching publisher links."""

from datetime import datetime, timezone

import pytest

from app.models import WatchlistEntry
from app.services.news_web_search import SEARCH_TOKEN_RESERVATION, OpenAIWebNewsDiscovery


def test_sandisk_search_returns_attributed_catalyst(monkeypatch):
    entry = WatchlistEntry(
        alpaca_asset_id="asset-sndk",
        symbol="SNDK",
        name="Sandisk Corporation Common Stock",
        exchange="NASDAQ",
    )
    answer = (
        "1. **Rosenblatt starts coverage of Sandisk at Buy with a $2,400 target.** "
        "([publisher])\n2. **Micron announces results.** ([other])"
    )
    response = {
        "status": "completed",
        "usage": {"total_tokens": 100},
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": answer,
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://publisher.example/sndk",
                                "title": "Rosenblatt starts coverage of Sandisk at Buy",
                                "start_index": answer.index("([publisher])"),
                            },
                            {
                                "type": "url_citation",
                                "url": "https://publisher.example/other",
                                "title": "Micron announces results",
                                "start_index": answer.index("([other])"),
                            },
                        ],
                    }
                ],
            },
        ],
    }
    discovery = OpenAIWebNewsDiscovery()
    monkeypatch.setattr(discovery, "available", lambda: True)
    monkeypatch.setattr(discovery, "_request", lambda payload: response)
    monkeypatch.setattr(discovery, "_reserve", lambda: datetime(2026, 9, 22, tzinfo=timezone.utc).date())
    monkeypatch.setattr(discovery, "_settle", lambda day, actual: None)
    items = discovery.search(
        entry, datetime(2026, 9, 22, tzinfo=timezone.utc), datetime(2026, 9, 23, tzinfo=timezone.utc)
    )

    assert len(items) == 1
    assert items[0].url == "https://publisher.example/sndk"
    assert items[0].title == "Rosenblatt starts coverage of Sandisk at Buy"
    assert items[0].excerpt == ""
    assert items[0].published_at is None
    assert items[0].symbols == ()


def test_search_heading_alone_cannot_make_unrelated_publisher_title_a_source(monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-mu", symbol="MU", name="Micron", exchange="NASDAQ")
    answer = "1. **Micron will report earnings.** ([publisher])"
    discovery = OpenAIWebNewsDiscovery()
    monkeypatch.setattr(discovery, "available", lambda: True)
    monkeypatch.setattr(discovery, "_reserve", lambda: datetime(2026, 9, 27, tzinfo=timezone.utc).date())
    monkeypatch.setattr(discovery, "_settle", lambda day, actual: None)
    monkeypatch.setattr(
        discovery,
        "_request",
        lambda payload: {
            "status": "completed",
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": answer,
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/general-market",
                                    "title": "General market outlook",
                                    "start_index": answer.index("([publisher])"),
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    )

    assert (
        discovery.search(
            entry,
            datetime(2026, 9, 20, tzinfo=timezone.utc),
            datetime(2026, 9, 27, tzinfo=timezone.utc),
        )
        == []
    )


def test_search_rejects_uncited_output(monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk", exchange="NASDAQ")
    discovery = OpenAIWebNewsDiscovery()
    monkeypatch.setattr(discovery, "available", lambda: True)
    monkeypatch.setattr(
        discovery,
        "_request",
        lambda payload: {
            "status": "completed",
            "usage": {"total_tokens": 100},
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Sandisk upgraded", "annotations": []}],
                },
            ],
        },
    )
    monkeypatch.setattr(discovery, "_reserve", lambda: datetime(2026, 9, 22, tzinfo=timezone.utc).date())
    monkeypatch.setattr(discovery, "_settle", lambda day, actual: None)
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    assert discovery.search(entry, now, now) == []


def test_incomplete_search_records_provider_reason(monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk", exchange="NASDAQ")
    discovery = OpenAIWebNewsDiscovery()
    monkeypatch.setattr(discovery, "available", lambda: True)
    monkeypatch.setattr(discovery, "_reserve", lambda: datetime(2026, 9, 27, tzinfo=timezone.utc).date())
    monkeypatch.setattr(discovery, "_settle", lambda day, actual: None)
    monkeypatch.setattr(
        discovery,
        "_request",
        lambda payload: {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "usage": {"total_tokens": 900},
            "output": [],
        },
    )

    with pytest.raises(ValueError, match="incomplete: max_output_tokens"):
        discovery.search(
            entry, datetime(2026, 9, 20, tzinfo=timezone.utc), datetime(2026, 9, 27, tzinfo=timezone.utc)
        )


def test_output_limit_retries_once_with_separate_budget_reservation(monkeypatch):
    entry = WatchlistEntry(alpaca_asset_id="asset-sndk", symbol="SNDK", name="Sandisk", exchange="NASDAQ")
    discovery = OpenAIWebNewsDiscovery()
    day = datetime(2026, 9, 27, tzinfo=timezone.utc).date()
    monkeypatch.setattr(discovery, "available", lambda: True)
    events = []

    def reserve():
        events.append("reserve")
        return day

    monkeypatch.setattr(discovery, "_reserve", reserve)
    settled = []

    def settle(reserved_day, actual):
        events.append("settle")
        settled.append(actual)

    monkeypatch.setattr(discovery, "_settle", settle)
    payloads = []

    def response(payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "usage": {"total_tokens": 900},
                "output": [],
            }
        return {
            "status": "completed",
            "usage": {"total_tokens": 1200},
            "output": [{"type": "web_search_call", "status": "completed"}],
        }

    monkeypatch.setattr(discovery, "_request", response)
    assert (
        discovery.search(
            entry, datetime(2026, 9, 20, tzinfo=timezone.utc), datetime(2026, 9, 27, tzinfo=timezone.utc)
        )
        == []
    )
    assert [payload["max_output_tokens"] for payload in payloads] == [25_000, 40_000]
    assert SEARCH_TOKEN_RESERVATION > 40_000
    assert settled == [900, 1200]
    assert events == ["reserve", "settle", "reserve", "settle"]
