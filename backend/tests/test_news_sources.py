"""Adapter behavior for direct releases, provider pagination, and indirect exposure."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.config import settings
from app.models import WatchlistEntry
from app.services.news_sources import (
    ArticleMetadata,
    alpaca_items,
    gdelt_exposure_items,
    rss_items,
    same_company_name,
    spglobal_index_items,
)


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        raw = self.responses.pop(0)
        return SimpleNamespace(
            content=raw if isinstance(raw, bytes) else b"",
            text=raw if isinstance(raw, str) else raw.decode() if isinstance(raw, bytes) else "",
            json=lambda: raw,
        )


def test_rss_release_retains_original_publication_time_and_summary():
    feed = (
        b"<rss><channel><item><title>Acme wins contract</title>"
        b"<link>https://example.com/release?utm_source=feed</link>"
        b"<description>&lt;p&gt;Acme signed a supply deal.&lt;/p&gt;</description>"
        b"<pubDate>Thu, 24 Sep 2026 16:05:00 -0400</pubDate></item></channel></rss>"
    )
    items = rss_items(FakeHttp([feed]), "https://example.com/feed", "company")
    assert len(items) == 1
    assert items[0].url == "https://example.com/release"
    assert items[0].excerpt == "Acme signed a supply deal."
    assert items[0].published_at == datetime(2026, 9, 24, 20, 5, tzinfo=timezone.utc)


def test_alpaca_pages_until_exhaustion_and_keeps_original_creation_time(monkeypatch):
    monkeypatch.setattr(settings, "alpaca_api_key", "test")
    monkeypatch.setattr(settings, "alpaca_api_secret", "test")
    responses = [
        {
            "news": [
                {
                    "id": 1,
                    "url": "https://example.com/1",
                    "headline": "Acme target raised",
                    "created_at": "2026-09-24T20:00:00Z",
                    "symbols": ["ACME"],
                    "summary": "Target raised",
                }
            ],
            "next_page_token": "page2",
        },
        {
            "news": [
                {
                    "id": 2,
                    "url": "https://example.com/2",
                    "headline": "Acme deal",
                    "created_at": "2026-09-24T21:00:00Z",
                    "symbols": ["ACME"],
                }
            ]
        },
    ]
    http = FakeHttp(responses)
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    items = alpaca_items(http, ["ACME"], datetime(2026, 9, 24, tzinfo=timezone.utc), now)
    assert [item.key for item in items] == ["1", "2"]
    assert http.calls[1][1]["params"]["page_token"] == "page2"
    assert items[0].published_at == datetime(2026, 9, 24, 20, tzinfo=timezone.utc)


def test_geopolitical_discovery_is_limited_to_configured_exposures():
    entries = [
        WatchlistEntry(alpaca_asset_id="asset-oil", symbol="OILX", name="Oil Producer", exchange="NYSE"),
        WatchlistEntry(alpaca_asset_id="asset-tech", symbol="TECH", name="Tech Company", exchange="NASDAQ"),
    ]
    http = FakeHttp([{"articles": [{"url": "https://example.com/oil", "title": "Oil supply disrupted"}]}])
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    items = gdelt_exposure_items(
        http,
        entries,
        {"OILX": ["oil_producer"]},
        datetime(2026, 9, 24, tzinfo=timezone.utc),
        now,
    )
    assert len(http.calls) == 1
    assert items[0].symbols == ("OILX",)
    assert items[0].published_at is None


def test_publisher_metadata_keeps_excerpt_and_verified_time():
    metadata = ArticleMetadata()
    metadata.feed(
        '<meta property="og:description" content="Acme signs an equipment deal">'
        '<meta property="article:published_time" content="2026-09-24T16:05:00-04:00">'
    )
    assert metadata.description == "Acme signs an equipment deal"
    assert metadata.published == datetime(2026, 9, 24, 20, 5, tzinfo=timezone.utc)


def test_sec_identity_rejects_a_reused_ticker_with_a_different_company_name():
    assert same_company_name("Advanced Micro Devices, Inc.", "Advanced Micro Devices Inc")
    assert not same_company_name("Different Industries Inc.", "Advanced Micro Devices Inc")


def test_official_sp_index_archive_extracts_watched_company_and_effective_date():
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    archive = (
        '<ul class="wd_item_list"><li class="wd_item"><div class="wd_title">'
        '<a href="https://press.spglobal.com/release-1">Acme Set to Join S&amp;P 500</a>'
        "</div></li></ul>"
    )
    page = (
        '<meta property="og:description" content="Effective October 5, 2026">'
        '<div class="wd_body wd_news_body">Acme Corp will join S&amp;P 500 '
        "effective prior to open of trading on October 5, 2026.</div>"
    )
    items = spglobal_index_items(FakeHttp([archive, page]), [entry])
    assert len(items) == 1
    assert items[0].provider == "spdji"
    assert items[0].symbols == ("ACME",)
    assert "October 5, 2026" in items[0].excerpt
