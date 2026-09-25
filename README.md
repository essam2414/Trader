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

For AI summaries, install [Ollama](https://ollama.com/download), run `ollama pull qwen3:4b`, and keep Ollama running locally. If the model is unavailable, source headlines remain visible with **Summary pending** and are retried on later runs. The model receives only source excerpts and watchlist identities; it does not receive Trading212 credentials.

Set `SEC_USER_AGENT` to an identifying name and contact address to enable SEC filings. A free `ALPHA_VANTAGE_API_KEY` enables estimated earnings dates; without it, earnings appear only when an official calendar feed is configured. Configure official company RSS/Atom feeds in `NEWS_IR_FEEDS_JSON` as a JSON object of provider name to URL. Configure official company iCalendar feeds in `NEWS_IR_EVENT_FEEDS_JSON` as a JSON object of watched ticker to URL. These are optional because companies publish different formats. The default sources are GDELT discovery, PR Newswire RSS, GlobeNewswire public-company and catalyst feeds, S&P Global's public index-announcement archive, and the existing Alpaca feed; official Fed, BLS, BEA and EIA schedules supply macro events.

Indirect geopolitical headlines are searched only for verified exposures in `NEWS_EXPOSURES_JSON`, for example `{"XOM":["oil_producer"],"AAL":["airline_fuel"]}`. Supported tags are `oil_producer`, `airline_fuel`, `semiconductor_exports`, and `china_sales`. Without a tag, the system requires a direct company match. Review company feed URLs and exposure tags when the watchlist changes.

The feed is intentionally a twice-daily briefing. A story found through GDELT may have only its publisher title until another source supplies text; the app labels unavailable summaries and links to the original article. Free sources can miss analyst changes and do not guarantee the earliest public release. The Events pane marks estimated dates and later date changes, and never assumes an earnings-call time from a date-only calendar entry.
