"""Adapter behavior for direct releases, provider pagination, and indirect exposure."""

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from app.config import settings
from app.models import WatchlistEntry
from app.services.news_sources import (
    ArticleMetadata,
    alpaca_items,
    bloom_energy_items,
    company_match,
    finnhub_items,
    form4_sale_details,
    gdelt_exposure_items,
    rss_items,
    same_company_name,
    sec_items,
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


def test_company_feed_symbol_and_formal_watchlist_names_match_releases():
    feed = (
        b"<rss><channel><item><title>AMD announces strategic partnership</title>"
        b"<link>https://ir.amd.com/release</link></item></channel></rss>"
    )
    items = rss_items(FakeHttp([feed]), "https://ir.amd.com/rss", "ir_amd", ("AMD",))
    assert items[0].symbols == ("AMD",)
    entry = WatchlistEntry(
        alpaca_asset_id="asset-fps",
        symbol="FPS",
        name="Forgent Power Solutions, Inc.",
        exchange="NYSE",
    )
    assert company_match("Forgent Power Solutions Announces Public Offering", entry)
    assert not company_match("Unrelated power company announces offering", entry)


def test_formal_vertiv_name_matches_its_index_announcement():
    entry = WatchlistEntry(
        alpaca_asset_id="asset-vrt",
        symbol="VRT",
        name="Vertiv Holdings Co Class A Common Stock",
        exchange="NYSE",
    )
    assert company_match("S&P 500 Addition Vertiv Holdings VRT Industrials", entry)


def test_bloom_energy_uses_official_newsroom_when_its_rss_feed_is_forbidden():
    feed_url = "https://investor.bloomenergy.com/rss/pressrelease.aspx"
    newsroom_url = "https://www.bloomenergy.com/newsroom/"
    html = """
    <article class="dp-dfg-item news_type-press-release">
      <h5><a href="https://www.bloomenergy.com/news/bloom-expands-contract/">
        Bloom Energy expands power contract
      </a></h5><div class="blogdate">September 25, 2026</div>
    </article>
    <article class="dp-dfg-item news_type-in-the-news">
      <h5><a href="https://www.bloomenergy.com/news/other/">Unrelated article</a></h5>
    </article>
    <article class="dp-dfg-item news_type-press-release">
      <h5><a href="https://www.bloomenergy.com/news/old-contract/">Old Bloom contract</a></h5>
      <div class="blogdate">September 1, 2026</div>
    </article>
    """

    class BlockedFeedHttp:
        calls = []

        def get(self, url):
            self.calls.append(url)
            if url == feed_url:
                request = httpx.Request("GET", url)
                raise httpx.HTTPStatusError(
                    "403 Forbidden", request=request, response=httpx.Response(403, request=request)
                )
            return SimpleNamespace(text=html)

    http = BlockedFeedHttp()
    items = bloom_energy_items(http, feed_url, ("BE",), datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert http.calls == [feed_url, newsroom_url]
    assert len(items) == 1
    assert items[0].provider == "ir_be"
    assert items[0].url == "https://www.bloomenergy.com/news/bloom-expands-contract"
    assert items[0].title == "Bloom Energy expands power contract"
    assert items[0].symbols == ("BE",)
    assert items[0].published_at is None


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


def test_industry_discovery_requires_explicit_sector_exposure():
    entries = [
        WatchlistEntry(alpaca_asset_id="asset-chip", symbol="CHIP", name="Chip Maker", exchange="NASDAQ"),
        WatchlistEntry(alpaca_asset_id="asset-soft", symbol="SOFT", name="Software Maker", exchange="NASDAQ"),
    ]
    http = FakeHttp([{"articles": [{"url": "https://example.com/capex", "title": "GPU supply expands"}]}])
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    items = gdelt_exposure_items(http, entries, {"CHIP": ["ai_infrastructure"]}, now, now)
    assert len(http.calls) == 1
    assert "GPU supply" in http.calls[0][1]["params"]["query"]
    assert items[0].symbols == ("CHIP",)


def test_finnhub_company_news_keeps_publisher_link_and_related_watchlist_symbols(monkeypatch):
    monkeypatch.setattr(settings, "finnhub_api_key", "test-key")
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    http = FakeHttp(
        [
            [
                {
                    "id": 17,
                    "url": "https://publisher.example/target?utm_source=feed",
                    "headline": "Broker raises CHIP price target",
                    "summary": "Target raised to $42.",
                    "datetime": 1790251200,
                    "related": "CHIP, SOFT",
                }
            ]
        ]
    )
    items = finnhub_items(http, "CHIP", now, now)
    assert http.calls[0][0] == "https://api.finnhub.io/api/v1/company-news"
    assert http.calls[0][1]["headers"] == {"X-Finnhub-Token": "test-key"}
    assert items[0].url == "https://publisher.example/target"
    assert items[0].symbols == ("CHIP", "SOFT")
    assert items[0].published_at is not None


def test_form4_only_treats_reported_sales_as_insider_sales():
    sale = """<ownershipDocument><reportingOwner><reportingOwnerId>
        <rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId></reportingOwner>
        <nonDerivativeTable><nonDerivativeTransaction>
        <transactionDate><value>2026-09-24</value></transactionDate>
        <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>42.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
        </transactionAmounts></nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
    assert "Jane Doe: 10000 shares at 42.50 per share" in form4_sale_details(sale)
    assert form4_sale_details(sale.replace("<transactionCode>S", "<transactionCode>F")) == ""
    assert form4_sale_details(sale.replace("<value>D</value>", "<value>A</value>")) == ""


def test_sec_adds_sales_and_registration_without_claiming_completed_dilution(monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", "Trader Research contact@example.com")
    entry = WatchlistEntry(alpaca_asset_id="asset-acme", symbol="ACME", name="Acme Corp", exchange="NASDAQ")
    mapping = {
        "fields": ["ticker", "exchange", "name", "cik"],
        "data": [["ACME", "NASDAQ", "Acme Corp", 1234]],
    }
    recent = {
        "filings": {
            "recent": {
                "form": ["4", "S-3"],
                "acceptanceDateTime": ["2026-09-24T20:00:00Z", "2026-09-24T19:00:00Z"],
                "accessionNumber": ["0001-01-000001", "0001-01-000002"],
                "primaryDocument": ["xslF345X06/ownership.xml", "registration.htm"],
            }
        }
    }
    sale = """<ownershipDocument><nonDerivativeTransaction>
        <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>10000</value></transactionShares>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
        </transactionAmounts></nonDerivativeTransaction></ownershipDocument>"""
    http = FakeHttp([mapping, recent, sale, "<p>Registration statement for common shares.</p>"])
    items = sec_items(http, [entry], datetime(2026, 9, 23, tzinfo=timezone.utc))
    assert len(items) == 2
    assert "insider sale" in items[0].title
    assert "10000 shares" in items[0].excerpt
    assert items[0].url.endswith("/xslF345X06/ownership.xml")
    assert http.calls[2][0].endswith("/ownership.xml")
    assert items[1].title == "Acme Corp filed Form S-3"
    assert "Registration statement" in items[1].excerpt


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
        '<a href="https://press.spglobal.com/2026-09-24-acme-release">Acme Set to Join S&amp;P 500</a>'
        "</div></li></ul>"
    )
    page = (
        '<meta property="og:description" content="Effective October 5, 2026">'
        '<div class="wd_body wd_news_body">Acme Corp will join S&amp;P 500 '
        "effective prior to open of trading on October 5, 2026.</div>"
    )
    items = spglobal_index_items(
        FakeHttp([archive, page]), [entry], datetime(2026, 9, 26, tzinfo=timezone.utc)
    )
    assert len(items) == 1
    assert items[0].provider == "spdji"
    assert items[0].symbols == ("ACME",)
    assert "October 5, 2026" in items[0].excerpt


def test_sp_index_archive_skips_old_announcements_and_matches_all_watched_additions():
    entries = [
        WatchlistEntry(
            alpaca_asset_id="asset-vrt",
            symbol="VRT",
            name="Vertiv Holdings Co Class A Common Stock",
            exchange="NYSE",
        ),
        WatchlistEntry(
            alpaca_asset_id="asset-mu",
            symbol="MU",
            name="Micron Technology, Inc. Common Stock",
            exchange="NASDAQ",
        ),
        WatchlistEntry(alpaca_asset_id="asset-cohr", symbol="COHR", name="Coherent Corp.", exchange="NYSE"),
    ]
    archive = (
        '<ul class="wd_item_list">'
        '<li class="wd_item"><div class="wd_title"><a '
        'href="https://press.spglobal.com/2026-03-06-old-index-changes">Old index changes</a></div></li>'
        '<li class="wd_item"><div class="wd_title"><a '
        'href="https://press.spglobal.com/2026-09-25-new-index-changes">'
        "Companies Set to Join the S&amp;P 500</a></div></li></ul>"
    )
    page = (
        '<div class="wd_body wd_news_body">S&amp;P 100 Addition Micron Technology MU. '
        "S&amp;P 500 Addition Vertiv Holdings VRT. S&amp;P 500 Addition Coherent COHR.</div>"
    )
    http = FakeHttp([archive, page])
    items = spglobal_index_items(http, entries, datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert len(items) == 1
    assert set(items[0].symbols) == {"VRT", "MU", "COHR"}
    assert len(http.calls) == 2
