# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Phase 1 (Trading212 sync + portfolio dashboard) is implemented: a Python/FastAPI backend and a
Next.js/TypeScript frontend, both tested and buildable. See `docs/superpowers/plans/2026-09-19-trading212-dashboard-phase1.md`
for the phase 1 design and task breakdown. Phases 2+ (watchlist/news, charting/indicators,
opportunity scoring, coaching, push notifications) are not yet built — see "What this project
is" below for the full planned scope.

## Commands

Backend (run from `backend/`, with the virtualenv at `backend/.venv/` activated):
- Install deps: `pip install -r requirements-dev.txt`
- Run all tests: `python -m pytest -v`
- Run a single test: `python -m pytest tests/test_portfolio_router.py::test_get_current_portfolio_returns_account_and_positions -v`
- Run dev server: `uvicorn app.main:app --reload`
- Copy `.env.example` to `.env` and fill in real Trading212 API credentials and a random `DASHBOARD_API_KEY` before running.

Frontend (run from `frontend/`):
- Install deps: `npm install`
- Run tests: `npm run test`
- Run dev server: `npm run dev`
- Build: `npm run build`
- Copy `.env.local.example` to `.env.local`; `DASHBOARD_API_KEY` must match the backend's.

## What this project is

"Trader" is a swing-trading decision-support app — explicitly **not** an auto-trader — for a
solo user who trades a watchlist of AI hyperscaler stocks on Trading212. Its purpose is to
automate the research/monitoring work a swing trader does manually: tracking company news,
sector news, and macro/geopolitical events; eyeballing support/resistance; and reviewing past
trades for mistakes. Planned capabilities:

- Read-only portfolio dashboard synced from the Trading212 API
- A manually-curated watchlist with relevant news surfaced per stock
- Price charts with computed technical indicators (support/resistance at daily/monthly/yearly
  granularity, plus others to be chosen once real data is visible)
- An LLM-driven "opportunity score" per watchlist stock, combining news, macro/geopolitical
  context, and technicals
- Portfolio coaching: LLM analysis of the user's own Trading212 order history to surface
  mistakes and improvement tips
- Eventually, push notifications (web push / PWA) to a phone

## Architecture

**Implemented (phase 1):**

- **Backend** (`backend/app/`): FastAPI. `config.py` (env-based `Settings`), `trading212.py`
  (`Trading212Client` — HTTP Basic auth, wraps `GET /equity/account/summary` and
  `GET /equity/positions`), `db.py`/`models.py` (SQLAlchemy, `PortfolioSnapshot`), `auth.py`
  (shared-secret bearer-token dependency — single-user, no real auth system), `dependencies.py`
  (DB session + Trading212 client DI), `schemas.py` (Pydantic response models — the wire
  contract with the frontend), `routers/portfolio.py` (`GET /api/portfolio/current`,
  `GET /api/portfolio/history`), `scheduler.py` + `services/snapshot.py` (APScheduler job that
  periodically persists a portfolio snapshot), `main.py` (app wiring/lifespan). No Alembic yet —
  `Base.metadata.create_all()` is sufficient for the one table so far. SQLite locally,
  Postgres (Supabase) in production via `DATABASE_URL`.
- **Frontend** (`frontend/`): Next.js 14 App Router + TypeScript + Tailwind. `app/page.tsx` is an
  async Server Component (`export const dynamic = "force-dynamic"` — must never be statically
  prerendered, since it always needs live data and would otherwise fail the production build
  when no backend is reachable at build time) that fetches from the backend server-side via
  `lib/api.ts` — `BACKEND_URL`/`DASHBOARD_API_KEY` are deliberately NOT prefixed
  `NEXT_PUBLIC_`, so they never reach the browser; no CORS setup exists or is needed, since the
  browser never calls the backend directly. `lib/types.ts` mirrors `backend/app/schemas.py`
  field-for-field — keep them in sync when either changes. `components/` holds presentational
  components (`PortfolioSummary`, `PositionsTable`, `EquityCurveChart` — the latter is a
  `"use client"` component using `recharts`) that receive data as props, they don't fetch.
- Both apps are fully tested (pytest + respx on the backend, Vitest + Testing Library on the
  frontend) and TDD was used throughout — follow the same pattern for new work.
- Deployment: Dockerfile for the backend (Railway/Render), Vercel for the frontend, Supabase for
  Postgres — see the phase 1 plan doc for full deployment steps.

**Planned (not yet built):** watchlist + news feed (Alpaca News API, Finnhub), price charting
with support/resistance indicators (`lightweight-charts`), `pgvector`-based RAG opportunity
scoring and portfolio coaching via the Anthropic Claude API, push notifications (PWA/web push).
See the phase 1 plan doc and the original architecture brainstorm for the full rationale.

Scope is single-user for now; the schema/design should avoid blocking multi-tenancy later (e.g.
via Supabase Row-Level Security) without building full multi-tenant auth up front.
