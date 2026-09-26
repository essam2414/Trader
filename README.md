# Trader

Swing trading helper app — a read-only portfolio dashboard synced from Trading212.

## Running locally

**Backend** (from `backend/`):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env   # then fill in your Trading212 API key/secret and a random DASHBOARD_API_KEY
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Frontend** (from `frontend/`, in a second terminal):

```powershell
npm install
copy .env.local.example .env.local   # BACKEND_URL + the same DASHBOARD_API_KEY as the backend
npm run dev
```

Then open http://localhost:3000.

## Watchlist news and events

The dashboard's **News | Events** pane collects source-backed catalysts for stocks currently in the watchlist. The backend collects news at **08:55 and 20:30 America/New_York** daily, refreshes event schedules at 06:00, and catches up after startup. Keep the backend running at those times. The browser only reads saved results. A newly added watchlist stock triggers a background collection.

Existing local databases get the new tables on backend startup. For a database already managed by Alembic, run `.venv\Scripts\python.exe -m alembic upgrade head` before starting the backend.

For AI summaries, create an OpenAI project API key and put it in the backend-only `OPENAI_API_KEY` setting, then set `OPENAI_NEWS_ENABLED=true`. This is separate from a ChatGPT subscription. The default model is `gpt-5.4-mini` through the Responses API; `gpt-4.1-mini` is an allowed fallback and may be faster for simple extraction. No request is sent without both settings. Candidate stories are grouped before analysis, then one structured response builds each card from all collected source excerpts for that story and the affected watchlist identities. The backend validates source IDs, asset IDs, and numbers before publishing. All pending stories are eligible for analysis on each sync; the daily token budget determines how many requests can actually run. When analysis is unavailable or over budget, source headlines remain visible with **Summary pending** and are retried on a later run. Trading212 credentials are never sent to OpenAI.

`OPENAI_NEWS_DAILY_TOKEN_BUDGET` defaults to 2,400,000 tokens per UTC day, close to the reported 2.5 million-token shared mini-model incentive; it can be raised to 2,500,000. OpenAI resets that incentive at 00:00 UTC. The app reserves a conservative upper estimate before each request and records the API's actual token usage afterward in PostgreSQL. Unknown usage after a timeout counts at the full reservation. This protects only this app's traffic: other projects using the same OpenAI organization can consume the shared allowance. Confirm that data sharing and the incentive are active in the OpenAI project before enabling analysis, and set a project spending limit in OpenAI as an additional billing guard. The app makes no OpenAI web-search calls and sends only bounded, public source excerpts plus watchlist identifiers.

Set `SEC_USER_AGENT` to an identifying name and contact address to enable free SEC filings. The SEC adapter includes 8-K/6-K, 10-Q/10-K, registration statements and prospectus supplements, and Form 4 filings with reported sales; a registration is not itself proof of completed dilution, and a Form 4 sale does not reveal motive. An optional free Finnhub API key (`FINNHUB_API_KEY`) adds ticker-specific publisher-linked company news as a second aggregation source, which can improve discovery of analyst target changes. The app never requires a paid Finnhub plan; leave this key unset if the free account does not provide the endpoint. A free `ALPHA_VANTAGE_API_KEY` enables estimated earnings dates; without it, earnings appear only when an official calendar feed is configured. Configure official company RSS/Atom feeds in `NEWS_IR_FEEDS_JSON` as a JSON object of provider name to URL. Configure official company iCalendar feeds in `NEWS_IR_EVENT_FEEDS_JSON` as a JSON object of watched ticker to URL. These are optional because companies publish different formats. The default sources are GDELT discovery, PR Newswire RSS, GlobeNewswire public-company and catalyst feeds, S&P Global's public index-announcement archive, and the existing Alpaca feed; official Fed, BLS, BEA and EIA schedules supply macro events.

Name a company feed `ir_<lowercase ticker>` (for example, `ir_amd`) so its releases are linked to that watched ticker. For this watchlist, official press-release RSS links are published by [Forgent](https://ir.forgentpower.com/news-events/press-releases), [Bloom Energy](https://investor.bloomenergy.com/investor-resources/rss/default.aspx), [Marvell](https://investor.marvell.com/news-events/press-releases), and [AMD](https://ir.amd.com/news-events/press-releases). Add them to the local `.env`; other issuers without a verified RSS feed remain covered by SEC filings, general feeds, and ticker-specific discovery.

Indirect industry and geopolitical headlines are searched only for verified exposures in `NEWS_EXPOSURES_JSON`, for example `{"XOM":["oil_producer"],"AMD":["ai_infrastructure","semiconductor_exports"],"NOW":["enterprise_software"]}`. Supported tags are `oil_producer`, `airline_fuel`, `semiconductor_exports`, `china_sales`, `semiconductor_supply_chain`, `ai_infrastructure`, `enterprise_software`, `data_center_power`, `optical_interconnect`, `ai_memory`, and `data_center_storage`. These tags are opt-in because not every stock in an industry benefits from the same change. Without a tag, the system requires a direct company match. Review company feed URLs and exposure tags when the watchlist changes.

The feed is intentionally a twice-daily briefing. A story found through GDELT may have only its publisher title until another source supplies text; the app labels unavailable summaries and links to the original article. Free sources can miss analyst changes and do not guarantee the earliest public release. The Events pane marks estimated dates and later date changes, and never assumes an earnings-call time from a date-only calendar entry.
