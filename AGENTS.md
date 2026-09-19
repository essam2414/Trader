# Repository Guidelines

## Product and Structure

Trader is a local, read-only Trading212 decision-support app for swing trading; it must never place trades. The FastAPI API in `backend/app/` owns Trading212 access, calculations, sync jobs, and database writes. Routes live in `routers/`, business logic in `services/`, and pytest coverage in `backend/tests/`.

The Next.js 16 / React 19 frontend is in `frontend/`: App Router pages are under `app/`, reusable UI is in `components/`, shared API/types code is in `lib/`, and Vitest tests are colocated in `__tests__/`. Keep `frontend/lib/types.ts` aligned with Pydantic models in `backend/app/schemas.py`.

Use local PostgreSQL through `DATABASE_URL`. Do not add hosted deployment, Supabase, or GitHub integrations unless explicitly requested. `CLAUDE.md` is historical context; `AGENTS.md`, `.agents/skills/`, and `.codex/config.toml` are active Codex guidance.

## Commands and Quality

From `backend/`, run `python -m uvicorn app.main:app --reload`, `python -m pytest -v`, `ruff check .`, and `ruff format --check .`. From `frontend/`, use `npm ci` for a clean install, then `npm run dev`, `npm run lint`, `npm run test`, and `npm run build`.

Python targets 3.13: four spaces, type hints, `snake_case`, and Ruff's 110-character limit. TypeScript is strict: two spaces, `camelCase` values, and `PascalCase` components. Prefer Tailwind CSS 4 utilities. Add regression coverage for fixes: backend tests use `test_<feature>.py`; frontend tests use `<Unit>.test.tsx`. Run focused tests while working and relevant checks before handoff.

## Desktop UI and Financial Safety

The persistent sidebar in `components/Sidebar.tsx` links Dashboard, Positions, History, Watchlist, and Settings. Unimplemented routes use `components/UnderDevelopment.tsx`. This is desktop-first: retain the `min-w-[1024px]` shell and capped content widths; use flexible Grid/Flex layouts so larger monitors gain whitespace, not oversized controls.

Never expose credentials through `NEXT_PUBLIC_` variables or commit `.env` files. Preserve read-only Trading212 scope. Do not silently alter fee, tax, FX, or realised/unrealised P&L behaviour; add targeted tests. Prefer `Decimal` and database numeric types for new money fields.

## Codex Tools and Skills

Use Context7, configured in `.codex/config.toml`, when version-specific documentation matters. Select `diagnosing-bugs` for reported failures, `tdd` for test-first work, `codebase-design` or `domain-modeling` for design decisions, `code-review` for a defined change set, and `playwright` for browser validation. `ask-matt`, `grill-with-docs`, `improve-codebase-architecture`, and `setup-matt-pocock-skills` require explicit user invocation.
