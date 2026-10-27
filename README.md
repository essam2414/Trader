# Trader

> **Status: Under development** — features, calculations, and setup may change.

Trader is a local, read-only swing-trading decision-support dashboard for a Trading 212 Invest or Stocks ISA account. It brings current holdings together with portfolio history, trade and dividend analytics, a watchlist, market charts, and source-linked company news and events. It is for analysis and learning; it does not place, modify, or cancel trades.

This repository is public, but the application is designed for one user on a trusted local machine. It is not a hosted multi-user service. Do not publish API keys, account data, database files, or environment files. Keep the app bound to localhost and do not expose it to the internet as-is.

## What it does

- Reads the live account summary and open positions from Trading 212 when the dashboard loads.
- Periodically stores portfolio snapshots and imports order-fill and dividend history into the local database. The history importer is resumable and works through paginated batches.
- Calculates trade performance, realised P&L, dividends, drawdown, and related statistics from imported history.
- Provides a watchlist with market charts and descriptive stock analysis. Alpaca credentials enable these market-data features.
- Collects source-linked watchlist news and event dates in scheduled background jobs. Optional providers can add AI summaries and extra news/calendar coverage.
- Protects the dashboard with a local PIN login and protects backend API routes with a shared secret between the frontend server and backend.

## How data moves through the app

```text
Trading 212 API ── live account/positions ──┐
Trading 212 API ── fills/dividends ─────────┤
Alpaca / public news sources ───────────────┤
                                             v
                                    FastAPI backend
                             sync jobs, calculations, API
                                             |
                                             v
                                 Local PostgreSQL database
                                             ^
                                             |
Browser ── Next.js UI and server routes ────┘
                  (server adds backend bearer key)
```

The browser talks to the Next.js app. Next.js server-side routes call the FastAPI backend and attach `DASHBOARD_API_KEY`; that secret and all provider credentials remain server-side. The backend reads Trading 212 data and stores history and snapshots in PostgreSQL. Current account and positions are fetched live when requested, while historical analytics use data already imported into the database. No order-placement flow is implemented.

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
