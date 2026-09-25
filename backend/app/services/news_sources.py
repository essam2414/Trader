"""Free, read-only discovery sources for watched US equities."""

import hashlib
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

from ..config import settings
from ..models import WatchlistEntry


@dataclass(frozen=True)
class SourceItem:
    provider: str
    key: str
    url: str
    title: str
    excerpt: str
    published_at: datetime | None
    symbols: tuple[str, ...] = ()


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


class ArticleMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description = ""
        self.published = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        key = (values.get("property") or values.get("name") or "").lower()
        content = (values.get("content") or "").strip()
        if key in {"og:description", "description", "twitter:description"} and not self.description:
            self.description = plain_text(content, 1200)
        if key in {"article:published_time", "datepublished", "pubdate"} and not self.published:
            self.published = parse_date(content)


def plain_text(value: str, limit: int = 6000) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()[:limit]


def canonical_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return ""
    retained = [(key, val) for key, val in parse_qsl(parsed.query) if not key.lower().startswith("utm_")]
    retained = [(key, val) for key, val in retained if key.lower() not in {"fbclid", "gclid"}]
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", urlencode(retained), "")
    )


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{14}", value):
            return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        result = datetime.fromisoformat(value)
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def source_key(provider: str, url: str, external_id: str | None = None) -> str:
    if external_id:
        return external_id[:512]
    return hashlib.sha256(f"{provider}:{canonical_url(url)}".encode()).hexdigest()


def company_match(text: str, entry: WatchlistEntry) -> bool:
    """Require a name, or a ticker in an equity context; short common words are unsafe alone."""
    lower = text.lower()
    name = re.sub(
        r"\b(inc|corp|corporation|company|class|common|stock|holdings|plc|ltd)\b", "", entry.name.lower()
    )
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) >= 4 and name in lower:
        return True
    symbol = re.escape(entry.symbol)
    return bool(re.search(rf"(?:NASDAQ|NYSE|AMEX|ticker|shares of)\s*[:(]?\s*{symbol}\b", text, re.I))


def same_company_name(left: str, right: str) -> bool:
    ignored = {"inc", "corp", "corporation", "company", "class", "common", "stock", "plc", "ltd", "a", "b"}
    left_words = set(re.findall(r"[a-z0-9]+", left.lower())) - ignored
    right_words = set(re.findall(r"[a-z0-9]+", right.lower())) - ignored
    return (
        bool(left_words and right_words)
        and len(left_words & right_words) / max(len(left_words), len(right_words)) >= 0.6
    )


class NewsHttp:
    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "TraderWatchlistNews/1.0 (local research)"},
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_sec_request = 0.0

    def get(self, url: str, **kwargs: object) -> httpx.Response:
        for attempt in range(3):
            host = urlparse(url).hostname or ""
            if host == "sec.gov" or host.endswith(".sec.gov"):
                delay = 0.13 - (time.monotonic() - self._last_sec_request)
                if delay > 0:
                    time.sleep(delay)
                self._last_sec_request = time.monotonic()
            try:
                response = self.client.get(url, **kwargs)
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
                continue
            if response.status_code in {429, 502, 503, 504} and attempt < 2:
                retry_after = response.headers.get("retry-after", "")
                if retry_after.isdigit() and int(retry_after) > 5:
                    response.raise_for_status()
                delay = int(retry_after) if retry_after.isdigit() else attempt + 1
                time.sleep(delay)
                continue
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError("Source response exceeds size limit")
            return response
        raise RuntimeError("Exhausted source retries")

    def close(self) -> None:
        self.client.close()

    def _public_host(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        try:
            addresses = socket.getaddrinfo(parsed.hostname, None)
            return bool(addresses) and all(
                ipaddress.ip_address(address[4][0]).is_global for address in addresses
            )
        except (OSError, ValueError):
            return False

    def _robots_allow(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            try:
                response = self.client.get(f"{origin}/robots.txt", timeout=3, follow_redirects=False)
                if response.status_code == 404:
                    self._robots[origin] = None
                elif response.status_code == 200 and len(response.content) <= 100_000:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
                    self._robots[origin] = parser
                else:
                    return False
            except httpx.HTTPError:
                return False
        parser = self._robots[origin]
        return parser is None or parser.can_fetch("TraderWatchlistNews", url)

    def article_metadata(self, url: str) -> tuple[str, datetime | None]:
        """Read bounded public publisher metadata without retaining the article body."""
        for _ in range(3):
            if not self._public_host(url) or not self._robots_allow(url):
                return "", None
            try:
                with self.client.stream("GET", url, timeout=5, follow_redirects=False) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code != 200 or "text/html" not in response.headers.get(
                        "content-type", ""
                    ):
                        return "", None
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) >= 250_000:
                            break
                    metadata = ArticleMetadata()
                    metadata.feed(data.decode("utf-8", errors="ignore"))
                    return metadata.description, metadata.published
            except (httpx.HTTPError, ValueError):
                return "", None
        return "", None


def gdelt_items(
    http: NewsHttp, entries: list[WatchlistEntry], since: datetime, until: datetime
) -> list[SourceItem]:
    items: list[SourceItem] = []
    for entry in entries:
        name = re.sub(r"\b(Inc|Corp|Corporation|Class|Common Stock)\b", "", entry.name, flags=re.I)
        name = re.sub(r"\s+", " ", name).strip()
        if len(name) < 4:
            continue
        response = http.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": f'"{name}"',
                "mode": "artlist",
                "format": "json",
                "sort": "datedesc",
                "maxrecords": 75,
                "startdatetime": since.strftime("%Y%m%d%H%M%S"),
                "enddatetime": until.strftime("%Y%m%d%H%M%S"),
            },
        )
        for index, raw in enumerate(response.json().get("articles", [])):
            url = canonical_url(str(raw.get("url", "")))
            title = str(raw.get("title", "")).strip()
            if not url or not title:
                continue
            # GDELT's seendate is an index observation, not a verified release time.
            metadata = getattr(http, "article_metadata", None)
            excerpt, published = metadata(url) if callable(metadata) and index < 2 else ("", None)
            items.append(
                SourceItem("gdelt", source_key("gdelt", url), url, title, excerpt, published, (entry.symbol,))
            )
    return items


EXPOSURE_QUERIES = {
    "oil_producer": '"oil supply" OR "oil prices" OR "Iran sanctions" OR "OPEC production"',
    "airline_fuel": '"oil prices" OR "oil supply" OR "jet fuel"',
    "semiconductor_exports": '"semiconductor export restrictions" OR "chip sanctions" OR "chip tariffs"',
    "china_sales": '"China tariffs" OR "US China trade restrictions"',
}


def gdelt_exposure_items(
    http: NewsHttp,
    entries: list[WatchlistEntry],
    exposures: dict[str, list[str]],
    since: datetime,
    until: datetime,
) -> list[SourceItem]:
    """Find indirect developments only for explicitly configured exposure tags."""
    items: list[SourceItem] = []
    for tag, query in EXPOSURE_QUERIES.items():
        symbols = tuple(entry.symbol for entry in entries if tag in exposures.get(entry.symbol.upper(), []))
        if not symbols:
            continue
        response = http.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": f"({query})",
                "mode": "artlist",
                "format": "json",
                "sort": "datedesc",
                "maxrecords": 50,
                "startdatetime": since.strftime("%Y%m%d%H%M%S"),
                "enddatetime": until.strftime("%Y%m%d%H%M%S"),
            },
        )
        for index, raw in enumerate(response.json().get("articles", [])):
            url = canonical_url(str(raw.get("url", "")))
            title = str(raw.get("title", "")).strip()
            if url and title:
                metadata = getattr(http, "article_metadata", None)
                excerpt, published = metadata(url) if callable(metadata) and index < 2 else ("", None)
                items.append(
                    SourceItem("gdelt", source_key("gdelt", url), url, title, excerpt, published, symbols)
                )
    return items


def alpaca_items(http: NewsHttp, symbols: list[str], since: datetime, until: datetime) -> list[SourceItem]:
    if not settings.alpaca_api_key or not settings.alpaca_api_secret or not symbols:
        return []
    items: list[SourceItem] = []
    token: str | None = None
    for _ in range(10):
        params = {
            "symbols": ",".join(symbols),
            "start": since.isoformat(),
            "end": until.isoformat(),
            "limit": 50,
            "sort": "desc",
            "include_content": "true",
        }
        if token:
            params["page_token"] = token
        response = http.get(
            "https://data.alpaca.markets/v1beta1/news",
            params=params,
            headers={
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            },
        )
        payload = response.json()
        for raw in payload.get("news", []):
            url = canonical_url(str(raw.get("url", "")))
            if not url:
                continue
            items.append(
                SourceItem(
                    "alpaca",
                    source_key("alpaca", url, str(raw.get("id", ""))),
                    url,
                    str(raw.get("headline", ""))[:500],
                    plain_text(str(raw.get("content") or raw.get("summary") or "")),
                    parse_date(raw.get("created_at")),
                    tuple(str(symbol).upper() for symbol in raw.get("symbols", [])),
                )
            )
        token = payload.get("next_page_token")
        if not token:
            break
    return items


def rss_items(http: NewsHttp, url: str, provider: str) -> list[SourceItem]:
    root = ElementTree.fromstring(http.get(url).content)
    items: list[SourceItem] = []
    for node in root.findall(".//item") + root.findall("{http://www.w3.org/2005/Atom}entry"):

        def child(name: str) -> str:
            element = node.find(name)
            return "" if element is None else (element.text or "").strip()

        link = child("link")
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.get("href", "") if atom_link is not None else ""
        link = canonical_url(link)
        title = child("title") or child("{http://www.w3.org/2005/Atom}title")
        if not link or not title:
            continue
        description = child("description") or child("{http://www.w3.org/2005/Atom}summary")
        items.append(
            SourceItem(
                provider,
                source_key(provider, link),
                link,
                title,
                plain_text(description),
                parse_date(child("pubDate") or child("{http://www.w3.org/2005/Atom}published")),
            )
        )
    return items


def spglobal_index_items(http: NewsHttp, entries: list[WatchlistEntry]) -> list[SourceItem]:
    """Read official S&P index changes from its public press archive."""
    archive = "https://press.spglobal.com/index.php?category=784&l=50"
    html = http.get(archive).text
    if "wd_item_list" not in html:
        raise ValueError("S&P press archive structure changed")
    items = []
    pattern = re.compile(
        r'<li class="wd_item">.*?<div class="wd_title"><a href="([^"]+)">(.*?)</a>',
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        url = canonical_url(unescape(match.group(1)))
        title = plain_text(match.group(2), 500)
        if not url.startswith("https://press.spglobal.com/") or not re.search(
            r"\b(?:set to join|to join|added to|join the s&p|index changes)\b", title, re.I
        ):
            continue
        page = http.get(url).text
        body_start = page.find('class="wd_body wd_news_body')
        if body_start < 0:
            continue
        body = plain_text(page[body_start : body_start + 150_000], limit=25_000)
        matched = [entry for entry in entries if company_match(body, entry)]
        if not matched:
            continue
        metadata = ArticleMetadata()
        metadata.feed(page[:30_000])
        excerpt = f"{metadata.description} {body[:5500]}"[:6000]
        items.append(
            SourceItem(
                "spdji",
                source_key("spdji", url),
                url,
                title,
                excerpt,
                metadata.published,
                tuple(entry.symbol for entry in matched),
            )
        )
    return items


def sec_items(http: NewsHttp, entries: list[WatchlistEntry], since: datetime) -> list[SourceItem]:
    if not settings.sec_user_agent:
        return []
    headers = {"User-Agent": settings.sec_user_agent}
    mapping = http.get("https://www.sec.gov/files/company_tickers_exchange.json", headers=headers).json()
    fields = mapping.get("fields", [])
    rows = [dict(zip(fields, row, strict=False)) for row in mapping.get("data", [])]
    items: list[SourceItem] = []
    for entry in entries:
        matches = [
            row
            for row in rows
            if str(row.get("ticker", "")).upper() == entry.symbol.upper()
            and str(row.get("exchange", "")).upper() == entry.exchange.upper()
            and same_company_name(str(row.get("name", "")), entry.name)
        ]
        if len(matches) != 1:
            continue
        cik = str(matches[0]["cik"]).zfill(10)
        recent = http.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=headers).json()[
            "filings"
        ]["recent"]
        accepted = 0
        for index, form in enumerate(recent["form"]):
            if form not in {"8-K", "6-K", "10-Q", "10-K"}:
                continue
            published = parse_date(recent["acceptanceDateTime"][index])
            if published and published < since:
                break
            if accepted >= 20:
                break
            accession = recent["accessionNumber"][index]
            document = recent["primaryDocument"][index]
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"
            )
            title = f"{entry.name} filed Form {form}"
            try:
                body = plain_text(http.get(url, headers=headers).text)
            except (httpx.HTTPError, ValueError):
                body = ""
            items.append(SourceItem("sec", accession, url, title, body, published, (entry.symbol,)))
            accepted += 1
    return items


def configured_feeds() -> dict[str, str]:
    feeds: dict[str, str] = {
        "prnewswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
        "globenewswire_public": (
            "https://www.globenewswire.com/RssFeed/orgclass/1/"
            "feedTitle/GlobeNewswire%20-%20News%20about%20Public%20Companies"
        ),
        "globenewswire_analyst": (
            "https://www.globenewswire.com/RssFeed/subjectcode/3-Analyst%20Recommendations/"
            "feedTitle/GlobeNewswire%20-%20Analyst%20Recommendations"
        ),
        "globenewswire_contracts": (
            "https://www.globenewswire.com/RssFeed/subjectcode/7-Business%20Contracts/"
            "feedTitle/GlobeNewswire%20-%20Business%20Contracts"
        ),
        "globenewswire_earnings": (
            "https://www.globenewswire.com/RssFeed/subjectcode/13-Earnings%20Releases%20and%20Operating%20Results/"
            "feedTitle/GlobeNewswire%20-%20Earnings%20Releases%20and%20Operating%20Results"
        ),
        "globenewswire_mna": (
            "https://www.globenewswire.com/RssFeed/subjectcode/27-Mergers%20and%20Acquisitions/"
            "feedTitle/GlobeNewswire%20-%20Mergers%20and%20Acquisitions"
        ),
    }
    for raw in (settings.news_rss_feeds_json, settings.news_ir_feeds_json):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            feeds.update(
                {
                    str(key): str(url)
                    for key, url in parsed.items()
                    if len(str(key)) <= 40 and canonical_url(str(url))
                }
            )
    return feeds
