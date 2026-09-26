# Watchlist catalyst news and events: implementation plan

## Goal and decisions

Replace the dashboard's Alpaca-only headline list with a watchlist-only catalyst briefing. Run collection automatically twice every day, including weekends and days when the dashboard is closed; geopolitical news can break over a weekend. Combine free sources, keep one card per underlying development, and use a local AI model to write a concise headline and an evidence-based detail summary. Add a **News | Events** switch in the existing dashboard pane. Events contain upcoming, dated company and US-market developments; breaking or undated developments belong in News.

Keep the application read-only. Do not generate trade instructions, price predictions, or an "already priced in" judgment. The user will assess the price chart. The default design has no recurring provider or model fee, but requires the local backend and a local model to run on the user's computer. No free source promises complete or minute-level coverage.

Use the existing 20-equity watchlist as the sole stock universe. Broad US macro items may be shown as **US market** events; geopolitical news must have an evidenced connection to at least one current watchlist stock. Do not list unrelated market news.

## Source inventory and roles

| Source | News collected | Events collected | How to use it |
|---|---|---|---|
| [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | Original publisher links and titles for company, sector, and geopolitical reporting, including stories with no ticker tag. | None. | Search each watched company's name, aliases and ticker **with company context**, over an overlapping time window. Also search a small set of geopolitical themes and filter them against verified stock exposure. Use article-list results as *discovery*, not proof of every claim. GDELT's core data updates on a [15-minute cycle](https://gdeltproject.org/data.html); validate publication times against the original publisher where possible. |
| Company investor-relations releases and calendars | Official earnings, guidance, contracts, partnerships, product, management, and other company announcements. | Confirmed earnings/call dates, investor days, shareholder votes and other announced dates. | Maintain a per-company source configuration containing official IR releases URL, RSS/Atom URL if offered, and events URL. Prefer RSS/Atom; use a narrowly scoped, polite HTML parser only for permitted public pages. Record unsupported/unavailable feeds rather than silently claiming coverage. |
| [SEC EDGAR submissions](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Watchlist-company 8-K, 6-K, 10-Q and 10-K filings; extract material items and linked exhibits rather than displaying every filing. | Dates explicitly announced in a filing, such as a vote or transaction closing; **not** inferred future earnings dates. | Resolve ticker to CIK with the [SEC ticker/CIK mapping](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), confirm company identity, then poll `data.sec.gov/submissions/CIK##########.json` and retrieve relevant public filing documents. Use an identified User-Agent and obey [fair-access rules](https://www.sec.gov/about/developer-resources). Filings can confirm a press release already found elsewhere, so deduplicate them. |
| [PR Newswire RSS](https://www.prnewswire.com/rss/) and [GlobeNewswire RSS](https://www.globenewswire.com/newswire-press-release-content) | Additional direct company press releases. | Dates contained in those releases. | Use available public feeds, filter by verified company name/symbol, and link to the release. Do not assume every company or every release appears on both services; do not store or republish full copyrighted feeds. |
| Existing [Alpaca news endpoint](https://docs.alpaca.markets/us/reference/news-3) | Another discovery channel, including analyst headlines that free primary sources may miss. | None. | Keep it as a supplement. Query by current watchlist symbols with explicit start/end, page through results, and deduplicate against other sources. Do not use Alpaca's `updated_at` as the original release time. Its default end can be 15 minutes old without real-time entitlement. |
| [S&P Dow Jones Indices announcements](https://www.spglobal.com/spdji/en/media-center/news-announcements/) | Announced additions, deletions and changes affecting watched stocks. | Published effective dates. | Parse official announcements; emit an announcement News card and one future Event if a watched stock is named. |
| [USTR releases](https://ustr.gov/about-us/policy-offices/press-office/press-releases), US Treasury/OFAC, relevant FDA and [EIA releases](https://www.eia.gov/reports/upcoming.php) | Official tariff, sanctions, regulatory, drug-decision and energy developments. | Explicit effective dates and relevant scheduled agency releases. | Use only where a current watchlist company has documented exposure or the item is a major US-market catalyst. GDELT/publisher reporting remains necessary for wars and ceasefires that are not announced through a US agency. |
| [Alpha Vantage earnings calendar](https://www.alphavantage.co/documentation/) | None for the first version. | Candidate earnings dates for watchlist symbols. | Fetch its bulk CSV at most daily, filter locally to the watchlist, and label a date **estimated** until confirmed on the company's IR site. The normal [free limit is 25 calls/day](https://www.alphavantage.co/support/); do not use it for frequent news polling. |
| [Fed FOMC](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [BLS](https://www.bls.gov/schedule/2026/), [BEA](https://www.bea.gov/news/schedule), [EIA](https://www.eia.gov/petroleum/supply/weekly/schedule.php) | The actual announcement/release can become News when relevant. | Official decision and economic-release schedules. | Curate high-impact US items: FOMC decision, projections, press conference and minutes; CPI, payrolls, PPI, PCE, GDP; EIA oil inventories for relevant energy stocks. Store official time in `America/New_York`. Do not label an event a rate *hike* or *cut* before a decision. |

This mix deliberately includes both direct announcements and independent reporting. A company valuation milestone or sector narrative may only appear in a publisher story, while a contract or earnings release may appear on IR before it is discussed by an aggregator. **Do not add Google News RSS or another unofficial search feed as a required dependency**; such a feed can be tested later if the first set misses cases.

## Implement in this order

### 1. Establish the existing behavior and acceptance cases

Read `backend/app/routers/news.py`, `backend/app/alpaca_market_data.py`, `frontend/components/NewsSection.tsx`, `frontend/lib/types.ts`, and their news tests. The current route returns Alpaca records on demand; the frontend polls every five minutes only while visible. Preserve the dashboard layout and authenticated Next.js proxy, but replace the news contract and raw-data dialog.

Create a small fixture corpus before implementing: an after-close earnings release, a pre-market contract, a negative guidance change, an analyst upgrade/target change, a broad company story with no ticker tag, an index addition, an oil/sanctions story relevant to one stock, an irrelevant same-name story, and a duplicated press release/filing/news article. Include expected symbols, catalyst type, original time, sources and grouping. The corpus is the quality gate for the AI and deduplicator.

### 2. Define stock identity and exposure metadata

For every `WatchlistEntry`, keep the Alpaca asset ID and current symbol as the authoritative stock identity. Resolve and store SEC CIK where unambiguous; match exchange and company name, not ticker alone. Store official company name, useful aliases, optional IR URLs, and optional sector/exposure tags (for example oil producer, airline fuel costs, semiconductor exports, China sales). Ticker changes and share classes must be handled as identity updates, not a new company by assumption.

Populate name/CIK automatically where possible. Keep IR URLs and indirect exposure tags configurable in a local backend configuration or database table; the initial version need not expose an editor in Settings. If a stock has no verified exposure metadata, permit direct company-name matches but suppress speculative geopolitical links. When a stock is removed from the watchlist, hide its stock-specific cards and events immediately; retain source records for deduplication and audit. On addition, backfill a bounded recent window and refresh its calendar.

### 3. Add local PostgreSQL persistence and an Alembic migration

Use the repository's existing SQLAlchemy/Alembic setup and `DATABASE_URL`. Add at least these entities, with indexes and uniqueness constraints:

- `news_source_items`: provider, provider item ID or canonical URL, source title/URL, normalized title, original `published_at` if known, `first_seen_at`, provider `updated_at`, bounded extracted text, content hash, extraction status, and safe provenance metadata. Unique `(provider, provider_item_id)` or `(provider, canonical_url)`.
- `news_stories`: stable ID, factual card headline, short summary, detailed summary, catalyst category, `direction` (`upside|downside|mixed|unclear`), primary-source timestamp and its precision/basis, first detected time, last material update time, summary/model version and processing state. A direction is an editorial tag, never a predicted return.
- `news_story_sources` and `news_story_stocks`: many-to-many links retaining every supporting source and every matched watchlist asset. Do not use a comma-separated symbol field as the source of truth.
- `market_events` and `market_event_stocks`: type, title, date/time, `time_precision` (`exact|date_only|window`), `date_status` (`confirmed|estimated|changed|cancelled`), source URL, last verified time and linked watched stocks. A major US-wide event can have no stock links and a `scope=us_market` field.
- `news_sync_state`: provider/scope cursor, last attempt, last success, last error, and run metrics. Never advance one source's cursor when that source fails.

Store timestamps in UTC with timezone-aware database fields. Keep original source time distinct from detection and update times. A date-only earnings event must never be displayed as if it has a confirmed clock time. Avoid storing full third-party article bodies indefinitely; retain only what is needed for an attributable summary and links, consistent with source terms. `backend/app/main.py` currently calls `Base.metadata.create_all` on startup: do not let that pre-create the new tables before Alembic applies the revision. Make local PostgreSQL startup migration-driven (`alembic upgrade head` before launching) and verify the upgrade against an existing database; retain explicit `create_all` only in isolated test fixtures if needed.

Likely backend locations: new modules under `backend/app/services/news/` for adapters, normalization, grouping, analysis and orchestration; `backend/app/services/events/` for calendars; plus edits to `models.py`, `schemas.py`, `config.py`, `routers/news.py`, `scheduler.py`, `main.py`, and a new Alembic revision. Keep a small orchestration interface such as `run_news_sync(db, sources, analyser, now)` and `run_events_sync(db, sources, now)`; tests can substitute fake source and AI adapters. Add server-side settings for `NEWS_ENABLED`, run times, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `ALPHA_VANTAGE_API_KEY` and `SEC_USER_AGENT` or equivalents. No secret belongs in a `NEXT_PUBLIC_` variable.

### 4. Build small source adapters behind one collection interface

Define a source adapter interface such as `fetch(scope, since, until) -> list[SourceItem]`, with source-specific pagination, rate control and error handling inside each adapter. Add GDELT, IR/RSS, SEC, Alpaca and official-announcement adapters in the order above. Separate company calendars and official macro calendars as event adapters. The scheduler and UI must never know provider-specific response shapes.

For each request: set a timeout, retry temporary failures with bounded backoff, honor `429`/`Retry-After`, cap pages and payload sizes, and log truncation. Use per-company GDELT queries rather than one global top-results query so a busy name cannot displace the rest of the watchlist. Search both full company name and context-qualified ticker; reject ambiguous ticker-only matches such as ordinary words. Use a three-day overlap on routine runs and a bounded longer lookback after downtime. Treat malformed HTML, changed feeds, paywalls and unavailable sites as individual source failures, not a failure of the entire briefing.

For GDELT-discovered articles, retrieve the original public page only when fetching is permitted and safe. Allow only HTTP(S), block redirects to private/local addresses, limit response bytes and parsing time, and respect robots/source terms. Use the original publisher's readable text or snippet when available. If only a title exists, do **not** ask AI to invent a detailed story; show a limited source-title card linking out, or mark it pending corroboration.

### 5. Normalize, match and deduplicate before AI summarization

Normalize URLs by dropping tracking parameters, normalize title whitespace/case, and map provider IDs to canonical source records. Upsert exact duplicates first. Build candidate story groups using the same watched stock, overlapping publication period, catalyst category and specific factual entities (for example counterparty or transaction). Use title/text similarity only to suggest a group; a second release about a *different* contract must remain a different story. A filing and press release about one earnings result should join the same group.

Use AI only to resolve ambiguous **candidate** merges; require it to return source IDs and a shared factual event key. If uncertain, keep two cards and flag for later review. When a follow-up merely repeats a story, attach the new source to the existing card. When it adds a material new fact, update the existing card's detail and `last_material_update_at`. A separate later milestone (for example deal completion after deal announcement) may be a new card. Display one card per resulting story, not one per article.

Set the displayed release time from the earliest **verified original publication** supporting that story. If none is known, label the time **First found** rather than fabricating a release time. Revisions must not silently replace the original time.

### 6. Add a local AI analysis module

Use [Ollama's local chat API with JSON-schema-constrained output](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx) as the default no-subscription adapter. Keep model name and local URL in backend settings; start evaluation with a modest model such as [`qwen3:4b`](https://ollama.com/library/qwen3) and choose the smallest locally runnable model that passes the fixture corpus. Hardware is unknown, so do not hard-code a large model requirement. The adapter seam should allow a different model later without changing ingestion, database or frontend code. LangChain, LangGraph, vector storage and RAG are unnecessary for this bounded, twice-daily summarization task.

Run the model on one candidate story group at a time, with bounded source excerpts and numbered source IDs. Give it the current watchlist identities and verified exposure tags. Instruct it to treat web content as untrusted data and to ignore instructions embedded in articles. Require structured output, approximately:

```json
{
  "relevant": true,
  "affectedAssetIds": ["watchlist-asset-id"],
  "category": "earnings|guidance|deal|analyst|regulatory|index|macro|geopolitical|other",
  "direction": "upside|downside|mixed|unclear",
  "headline": "Factual, concise headline",
  "shortSummary": "One sentence for the card",
  "detailSummary": "A few short paragraphs describing what happened and the relevant context",
  "keyFacts": ["Specific supported facts, with numbers only if present in the evidence"],
  "unknowns": ["Material details the sources do not establish"],
  "relevanceReason": "Why each watched stock is affected",
  "supportingSourceIds": [123]
}
```

The model may classify relevance, category and direction, and write prose **only from provided evidence**. It must not invent dates, numbers, counterparties, quotes, source URLs or affected stocks. The backend, not the model, supplies release timestamps and source links. Reject results with unknown asset/source IDs, invalid enums, empty evidence, unsupported numbers, or missing mandatory fields; retry once with a shorter input, then mark the group for review. Store prompt/model version and source hashes to allow reprocessing after a real content change without generating duplicate cards. Limit concurrency and runtime so one slow local inference cannot block all collection.

If Ollama is down, keep collected items queued. Show clearly sourced, high-confidence direct releases with their original headline and **Summary pending** rather than hiding a potentially important item; do not publish an AI detail summary that failed validation. GDELT title-only leads can remain pending until corroborated. Never send Trading 212 credentials or unrelated account data to the model.

### 7. Build the Events collector separately

Ingest earnings calendar CSV once daily, company IR calendars, index announcements, and official Fed/BLS/BEA/EIA schedules. Extract only explicit future dates. Match earnings to the exact watched company; prefer its IR-confirmed time over an aggregator estimate. Include date/time precision and confirmation status. Recheck events daily and immediately when a supporting release changes. Upsert by stable entity + event type + reporting period or official event ID; do not create a duplicate because a date moves. Preserve previous date/status for audit, mark cancelled or postponed events clearly, and retire past events after an appropriate display period.

For the initial Events view include earnings/calls, investor days, watched-company votes and regulatory milestones when officially dated, index additions/effective dates, FOMC decisions and minutes, CPI, payrolls, PCE, GDP and relevant EIA petroleum releases. Add niche sector dates only when a reliable official source and a watched-stock connection exist. An unexpected war development belongs in News; an announced sanctions start date can additionally become an Event.

### 8. Schedule and monitor the runs

Extend the existing APScheduler setup in `backend/app/main.py`. Configure `America/New_York` so daylight-saving changes do not shift the US-market run times. Default news runs: **20:30 ET** (after the main after-hours window) and **08:55 ET** (before the 09:30 regular open, after common 08:30 data releases), every day; make times configurable. Refresh Events daily and whenever a watched company is added. A short, authenticated **Refresh now** action can be added if a morning item appears after 08:55; throttle it to protect free feeds.

On backend startup, run a catch-up sync if the last successful run is overdue; use overlapping time windows and upserts. The computer must be on for scheduled runs, and the UI must show the last successful run and partial-source failures. Configure `max_instances=1`, coalescing, sensible misfire handling, and a PostgreSQL advisory lock or equivalent so two backend processes cannot run the same collection simultaneously. Do not tie collection to whether the browser tab is open. Record per-source fetched count, accepted count, errors and duration without logging secrets or full article text.

### 9. Replace backend contracts and frontend types together

Keep authenticated read-only routes. Change `GET /api/news` to return a paginated list of story cards, add `GET /api/news/{id}` for the full sourced detail, `GET /api/events` for future events, and `GET /api/news/status` for freshness/partial failure state. An optional authenticated, throttled refresh route may trigger collection; it must not place trades. Define Pydantic output schemas in `backend/app/schemas.py` and matching strict TypeScript types in `frontend/lib/types.ts`. Remove `rawData` from the public news response.

List card fields: stable story ID, headline, short summary, watched symbols, category/direction, original release time or `null`, timestamp basis, first-found time, and update time. Detail fields add longer summary, supported key facts, material unknowns, relevance explanation, a source list with title/publisher/URL/published time, and a clear **Summary pending** state if applicable. Events include stable ID, title/type, scope, watched symbols, scheduled date/time, precision, confirmation status, source and last verified time. Never interpolate arbitrary source HTML into the page.

Likely frontend locations: extend the authenticated Next.js routes under `frontend/app/api/news/`, add `frontend/app/api/events/route.ts`, update `frontend/lib/types.ts`, and split `frontend/components/NewsSection.tsx` into a thin tab container plus focused card/detail/events modules if that reduces complexity. Keep the existing watchlist and dashboard page layout intact.

### 10. Update the dashboard pane

Change `frontend/components/NewsSection.tsx` to a two-tab **News | Events** pane while retaining the existing desktop grid, capped width and scrollable body. News cards should show watched ticker badges, a concise AI headline and short summary, category/direction label, and **Released [date/time]** or **First found [date/time]**. Sort primarily by original release time, with new material updates visibly marked; do not reorder a stale story to the top solely because a provider touched its record. Optional category filters can follow later.

Clicking a card opens an accessible detail dialog with the full AI summary, key facts and unknowns, why the watched stocks are linked, original and detection times, all corroborating source links, and a visible pending/error state. Replace the present raw-Alpaca-field dialog. Events cards show date/time and timezone, relevant symbols or **US market**, event type, confirmed/estimated status and official source; clicking one opens its source and date details. Render a user's local date/time (currently UK browser time) and label Eastern Time when shown; use the timezone-aware timestamp, not a fixed UK/US hour offset. Keep keyboard Escape, focus handling and clear empty/error states. Show last successful briefing and a warning if one source failed while other cards remain available. Continue lightweight UI polling for completed runs, but do not let frontend polling initiate provider requests.

### 11. Test behavior that protects the goal

Add backend fixtures and tests for every source adapter's normal response, pagination, rate-limit/timeout and malformed data; CIK/alias matching; exact and cross-source deduplication; unrelated companies and ambiguous ticker words; original-versus-detected timestamps; source cursor recovery after failure; changed or cancelled event dates; estimated-versus-confirmed earnings; and NY daylight-saving run times. Test AI schema validation with fake model responses, including fabricated source IDs/numbers, irrelevant results, prompt-injection text and model downtime. Test one complete pipeline run with fake sources and a fake model: several source articles about one catalyst yield one card with multiple citations; a separate catalyst remains separate.

Update `backend/tests/test_news.py` and add focused source, story and events tests. Update `frontend/components/__tests__/NewsSection.test.tsx` for tab switching, stock badges, correct time labels, one card per story, detailed sourced dialog, pending summary and partial failure. Run focused tests during implementation, then `python -m pytest -v`, `ruff check .`, `ruff format --check .`, `npm run lint`, `npm run test`, and `npm run build` as the repository requires.

### 12. Validate source coverage before calling the feature complete

Use the fixture corpus and a short live observation period against stories the user previously found in Trading 212 forums. For each expected catalyst record: first public source time, first time each free source exposed it, scheduled run that collected it, whether the AI kept it, whether the summary was faithful, and whether it formed exactly one card. Test at least one after-close earnings item, one pre-market release, one analyst item, one indirect/geopolitical item, one date change, and one unrelated headline. Report misses **by source versus matching/AI failure**; a missed source cannot be fixed by prompt changes. Keep the dashboard usable with partial-source errors.

## Known limits and decisions for the implementing model

- Twice-daily runs cannot capture an item released after the morning run until the next run. The optional throttled refresh addresses that without turning this into an expensive real-time system.
- Free sources will especially vary in analyst target coverage. Keep Alpaca for that category, measure missed cases, and only then consider a specialist paid feed.
- SEC filings can lag a company's first press release. Use them as evidence, not necessarily the card's release time.
- Publishers may restrict full text or automated access. A link/title with a pending summary is preferable to invented detail or unauthorized scraping.
- Some earnings dates are estimates. The UI must make that status obvious and never invent a call time.
- AI output is editorial summarization with source links; it is never an autonomous market-data source or a trade signal.
