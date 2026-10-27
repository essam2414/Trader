# Trader

> **Status: Under development** — features, calculations, and setup may change.

Trader is a local, read-only swing-trading decision-support dashboard for a Trading 212 Invest or Stocks ISA account. It brings current holdings together with portfolio history, trade and dividend analytics, a watchlist, market charts, and source-linked company news and events. It is for analysis and learning; it does not place, modify, or cancel trades.

The application is designed for one user on a trusted local machine. It is not a hosted multi-user service. Do not publish API keys, account data, database files, or environment files. Keep the app bound to localhost and do not expose it to the internet as-is.

## What it does

- Reads the live account summary and open positions from Trading 212 when the dashboard loads.
- Periodically stores portfolio snapshots and imports order-fill and dividend history into the local database. The history importer is resumable and works through paginated batches.
- Calculates trade performance, realised P&L, dividends, drawdown, and related statistics from imported history.
- Provides a watchlist with market charts and descriptive stock analysis. Alpaca credentials enable these market-data features.
- Builds a source-backed watchlist catalyst briefing with story grouping, novelty checks, and evidence-validated AI summaries. OpenAI analysis and web-search discovery are opt-in.
- Protects the dashboard with a local PIN login and protects backend API routes with a shared secret between the frontend server and backend.

## How data moves through the app

Trader is split into a browser-facing Next.js application, a Python API and background worker, and a local PostgreSQL database. The browser never connects directly to PostgreSQL or to the provider APIs that require server credentials.

```mermaid
flowchart LR
  Browser[Browser]
  subgraph Frontend[Next.js frontend]
    Pages[App Router pages and UI components]
    Routes[Server route handlers]
    Session[PIN session cookie]
    Pages --> Routes
    Browser --> Pages
    Browser -->|PIN login and session cookie| Session
    Session -->|Gates navigation| Pages
  end
  subgraph Backend[FastAPI backend]
    Routers[Authenticated API routers]
    Services[Portfolio, watchlist, market, news and event services]
    Scheduler[APScheduler background jobs]
    Routers --> Services
    Scheduler --> Services
  end
  DB[(Local PostgreSQL)]
  T212[Trading 212 API]
  Alpaca[Alpaca market data]
  Sources[News, filings and event sources]
  OpenAI[Optional OpenAI Responses API]
  Routes -->|Server-side request with bearer key| Routers
  Services <--> DB
  T212 -->|Read-only account and history data| Services
  Alpaca --> Services
  Services <-->|Read and public-source data| Sources
  Services <-->|Opt-in public-source analysis and discovery| OpenAI
```

### Code layers

| Area | Responsibility |
| --- | --- |
| `frontend/app/` | App Router pages and server-side API route handlers that forward browser requests to FastAPI |
| `frontend/components/` | Dashboard, positions, history, watchlist, charts, trends, and news/event UI |
| `frontend/lib/` | Backend request helpers, session handling, shared UI types, and watchlist route helpers |
| `backend/app/routers/` | HTTP endpoints for portfolio, watchlist, news/events, and market-session data |
| `backend/app/services/` | Portfolio metrics, history sync, watchlist and chart data, stock analysis, news collection/analysis, and event calendars |
| `backend/app/models.py` and `schemas.py` | PostgreSQL persistence models and validated API response shapes |
| `backend/app/scheduler.py` and `main.py` | Backend startup wiring and periodic/background jobs |
| `backend/alembic/` | Database schema migrations |
| `backend/tests/` and `frontend/**/__tests__/` | Backend and frontend regression coverage |

### Source-backed AI news pipeline

News is a central feature with a source collection and evidence-checking pipeline. Collection is scheduled for **08:55 and 20:30 America/New_York**. The backend also checks for missed runs after startup, retries pending summaries every five minutes, and persists source/run status so failures and queued work can be inspected.

1. **Collect candidate sources.** Adapters read Alpaca company news, SEC filings, S&P Global index announcements, default public RSS feeds, and any configured company investor-relations feeds. Finnhub is an optional extra source. OpenAI web search can optionally discover additional publisher URLs; it is off unless both OpenAI news and web search are explicitly enabled.
2. **Normalize and preserve provenance.** Each item is normalized to a canonical URL, provider/source identifier, headline, bounded excerpt, candidate symbols, publication date and date precision. Source identity and a content hash make ingestion idempotent. A revised article is retained as a new evidence revision rather than silently overwriting what an earlier analysis used.
3. **Filter and match to the watchlist.** The collector drops malformed items and items without a likely catalyst, then matches ticker/company references to the local watchlist. Indirect industry or geopolitical coverage is accepted only when a ticker has an explicit, configured exposure tag. Source items are saved with their original links and linked to one or more candidate stories and stocks.
4. **Group developments and check novelty.** Stable event descriptors and publication dates help distinguish new developments from multiple articles about the same event. Candidates with ambiguous identity are held for comparison against previously covered stories. If evidence describes additional coverage of an existing development, its sources are merged into the existing card while the decision and provenance remain stored; it does not create a duplicate card. Unresolved comparisons stay queued for a later retry or review.
5. **Generate one structured analysis per story.** When `OPENAI_API_KEY` is present and `OPENAI_NEWS_ENABLED=true`, the backend sends the selected watchlist identifiers and public source titles/excerpts for that story to the OpenAI Responses API. The model is asked for a headline, short and detailed summaries, relevance explanation, key facts, unknowns, category, direction, affected watchlist assets, and supporting source IDs. Source excerpts are treated as untrusted input. Trading 212 credentials, holdings, balances, and trade history are not sent to OpenAI.
6. **Validate before publication.** The response must match a strict schema. The backend verifies every referenced asset and source ID against the supplied watchlist and evidence, and checks that generated numbers appear in supporting source text. Responses that parse but fail provenance checks get one evidence-bounded correction attempt. Candidates with ambiguous identity also pass a historical coverage/novelty check before publication; unrelated items are discarded. Unsupported, ambiguous, or unavailable analyses are held rather than published as complete summaries.
7. **Persist, retry, and display.** PostgreSQL stores the raw source items, story cards, stock/source links, event identity and resolution decisions, comparison cache, sync status, collection runs, and daily AI usage. Pending candidates retain their source evidence while the status API reports their queue state and retry details; unresolved or held candidates are not shown as ready cards. Temporary failures receive a retry time, while repeated validation/ambiguity problems can be marked for review. The Next.js news UI calls authenticated FastAPI endpoints to show cards, source links, refresh/status information, and pending-analysis issues. The same cards can be filtered by watchlist stock in its detail pane.

AI summaries and optional OpenAI web discovery share a persistent UTC-day token budget, set to **2,400,000 tokens by default** and capped at 2,500,000 by the application. The backend reserves a conservative estimate before a request and settles it using reported usage afterward; unknown usage after a timeout is charged at the full reservation. OpenAI analysis is optional and may incur API charges. Without it, source headlines and links can still be collected and shown, with summaries marked pending.

### Event calendar pipeline

Upcoming events are collected separately from the AI news-card pipeline. A daily job reads public Fed, BLS, BEA, and EIA schedules, earnings-calendar data when configured, optional company investor-relations calendars, and relevant index events. Events and their watchlist-stock links are upserted locally with date/source metadata. Date-only or estimated events remain identified as such; the app does not invent an earnings-call time. The sidebar and news/events panel read the persisted event records through the API.

### Main data boundary

PostgreSQL is the local source of truth for imported history, snapshots, watchlist configuration, cached market history, and collected news/events. Current account/position values are fetched live; historical metrics and briefing cards are derived from local persisted records. The app has no order-placement flow and never writes trades to Trading 212.

## Tech stack

- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, Recharts
- **Backend:** Python 3.13, FastAPI, Pydantic Settings, SQLAlchemy, APScheduler
- **Database:** local PostgreSQL (via psycopg2); Alembic migrations are included
- **Market data:** Alpaca API and its IEX/delayed SIP feeds when configured
- **Testing tools:** pytest and Ruff for Python; Vitest and ESLint for TypeScript

## First-time local setup

These steps are for Windows PowerShell. You will need Python 3.13, Node.js with npm, and a local PostgreSQL server. The backend reads `backend/.env`; the frontend reads `frontend/.env.local`.

### 1. Create a read-only Trading 212 API key

In the Trading 212 app or website, open **Settings → API (Beta)**, accept the risk notice, and create a key. Select only the read permissions needed for account/portfolio data, orders/history, and dividends. Do not grant order placement or other write permissions. Copy both the API key and secret when shown; the secret is only displayed once. The public API currently supports Invest and Stocks ISA accounts. See Trading 212’s [API key instructions](https://helpcentre.trading212.com/hc/en-us/articles/14584770928157-How-can-I-generate-an-API-key) and [API documentation](https://docs.trading212.com/api).

### 2. Create a local PostgreSQL database

Start PostgreSQL, then use `psql` (or another PostgreSQL client) to create a local role and a new, empty database for this installation. For example, connect as a PostgreSQL administrator and run:

```sql
CREATE USER trader WITH PASSWORD 'choose-a-local-password';
CREATE DATABASE trader OWNER trader;
```

Use that password in the backend `DATABASE_URL` below. PostgreSQL must be running whenever you use Trader. The database is created on the user’s own computer and is not downloaded from or stored in this GitHub repository. Each user should create a separate empty database and connect their own Trading 212 account; this repository does not include my local database or account history.

### 3. Configure and start the backend

From the repository root:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set these required values:

```dotenv
TRADING212_API_KEY=your-read-only-trading212-key
TRADING212_API_SECRET=your-trading212-secret
TRADING212_BASE_URL=https://live.trading212.com/api/v0
DATABASE_URL=postgresql+psycopg2://trader:your-local-password@localhost:5432/trader
DASHBOARD_API_KEY=replace-with-a-long-random-secret
```

Use `https://demo.trading212.com/api/v0` instead if your key belongs to a Trading 212 demo account. Keep the API key and secret only in this backend file. `DASHBOARD_API_KEY` is a separate random secret shared with the frontend in the next step. Do not commit either environment file.

Start the backend from `backend/`:

```powershell
python -m uvicorn app.main:app --reload
```

On startup, the app creates missing database tables. For an existing database that is managed by Alembic, apply migrations first with `python -m alembic upgrade head` from `backend/`.

### 4. Configure and start the frontend

Open a second PowerShell window at the repository root:

```powershell
cd frontend
npm ci
Copy-Item .env.local.example .env.local
```

Edit `frontend/.env.local`:

```dotenv
BACKEND_URL=http://localhost:8000
DASHBOARD_API_KEY=the-same-random-secret-as-backend
```

Start the frontend from `frontend/`:

```powershell
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The current local login PIN is `9214`. This PIN is fixed in the application code, so this login is a convenience gate for a personal local install, not strong authentication for an internet-facing deployment.

### 5. Let the backend sync data

Keep both processes and PostgreSQL running. The dashboard requests current account and position data live from Trading 212. The backend writes a portfolio snapshot every 15 minutes and starts importing fills and dividends on its first history-sync interval (currently 60 minutes after backend startup); subsequent imports run hourly. Historical metrics populate as those imports complete. There is no manual sync control in the current UI. Leave the backend running for the first interval, then refresh the dashboard. Trading 212 API rate limits and the account’s available history can affect how quickly the initial import finishes; the importer continues in later batches.

## API keys and optional integrations

Only the Trading 212 API key and secret are required for the core portfolio features. Optional features use these backend-only settings:

| Setting | Needed for | Required? |
| --- | --- | --- |
| `ALPACA_API_KEY`, `ALPACA_API_SECRET` | Watchlist market data, charts, and stock analysis | Optional; needed for these features |
| `OPENAI_API_KEY` plus `OPENAI_NEWS_ENABLED=true` | AI-generated news summaries | Optional; disabled by default; usage may incur charges |
| `FINNHUB_API_KEY` | Additional company-news source | Optional |
| `ALPHA_VANTAGE_API_KEY` | Estimated earnings dates | Optional |
| `SEC_USER_AGENT` | Identifying user-agent for free SEC filing data; include a contact address | Optional, recommended for SEC requests |

Official company news feeds, event calendars, and verified company exposure tags can also be configured with `NEWS_IR_FEEDS_JSON`, `NEWS_IR_EVENT_FEEDS_JSON`, and `NEWS_EXPOSURES_JSON`. Defaults and examples are in [`backend/.env.example`](backend/.env.example). Without optional provider keys, core Trading 212 portfolio data still works, but related market-data or news enhancements may be unavailable. Never put secrets in `NEXT_PUBLIC_` variables.

## Useful commands

From `backend/`:

```powershell
python -m pytest -v
ruff check .
ruff format --check .
```

From `frontend/`:

```powershell
npm run lint
npm run test
npm run build
```

## Financial and data scope

Trader is decision-support software, not financial advice. Its calculations depend on the available broker history and should be checked against Trading 212 statements. It is read-only by design and must never place trades. Trading 212 credentials and imported account information are sensitive: use a read-only key, keep the repository’s ignored environment files local, and revoke the key in Trading 212 if it is exposed.
