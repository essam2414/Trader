# Repository Guidelines

## Project Structure & Module Organization

Trader is a read-only Trading212 portfolio dashboard. The FastAPI backend lives in `backend/app/`; API routes are in `routers/`, business logic in `services/`, and pytest coverage in `backend/tests/`. The Next.js 14 frontend lives in `frontend/`: App Router pages are under `app/`, reusable UI under `components/`, shared API/types/helpers under `lib/`, and Vitest files are colocated in `__tests__/`. Design notes and implementation plans belong in `docs/superpowers/`. CI is defined in `.github/workflows/ci.yml`.

Keep `frontend/lib/types.ts` synchronized with Pydantic response models in `backend/app/schemas.py`. Components should receive data as props; server-side fetching belongs in `lib/api.ts` or App Router server components.

## Build, Test, and Development Commands

Run backend commands from `backend/`:

- `pip install -r requirements-dev.txt` installs runtime and development dependencies.
- `python -m uvicorn app.main:app --reload` starts the API locally.
- `python -m pytest -v` runs all backend tests.
- `ruff check .` and `ruff format --check .` match CI lint and formatting checks.

Run frontend commands from `frontend/`:

- `npm ci` performs a lockfile-exact install (`npm install` is suitable when updating dependencies).
- `npm run dev` starts Next.js on port 3000.
- `npm run test`, `npm run lint`, and `npm run build` reproduce frontend CI checks.

## Coding Style & Naming Conventions

Python targets 3.13, uses four-space indentation, type hints, and Ruff (`E`, `F`, `I`; 110-character lines). Use `snake_case` for functions/modules and `PascalCase` for classes. TypeScript uses strict typing, two-space indentation, `camelCase` values, and `PascalCase` React components/files. Prefer Tailwind utility classes and named component exports. Never expose backend credentials through `NEXT_PUBLIC_` variables.

## Testing Guidelines

Use pytest and respx for backend tests; name files `test_<feature>.py` and tests `test_<behavior>`. Use Vitest plus Testing Library for frontend behavior, with `<Unit>.test.ts(x)` names. Add regression tests with fixes and cover success, error, and boundary cases. Run the relevant focused test while developing, then the complete suite before submission.

## Commit & Pull Request Guidelines

History follows Conventional Commit prefixes such as `feat:`, `fix:`, and `docs:`. Keep commits focused and subjects imperative. Pull requests should explain the change and validation performed, link relevant issues or design documents, and include screenshots for UI changes. Ensure lint, tests, formatting, and the production build pass before requesting review.

## Security & Configuration

Copy `backend/.env.example` to `.env` and `frontend/.env.local.example` to `.env.local`. Use the same `DASHBOARD_API_KEY` in both, never commit secrets or local databases, and preserve the backend's read-only Trading212 scope.
