# Trading212 Sync + Portfolio Dashboard (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the chosen tech stack end to end and ship a working web dashboard that shows the user's live Trading212 Invest account performance (total value, cash, unrealized P/L, open positions) plus a simple value-over-time chart built from periodic snapshots.

**Architecture:** A Python FastAPI backend authenticates to the Trading212 API (Basic auth with an API key/secret pair, read-only scopes), exposes two endpoints (`/api/portfolio/current` for a live proxy of account+positions, `/api/portfolio/history` for stored snapshots), and runs a background job every N minutes that persists a snapshot to Postgres/SQLite via SQLAlchemy. A Next.js (App Router) frontend renders the dashboard as a Server Component that fetches directly from the FastAPI backend during server-side rendering — the backend's shared-secret API key stays server-side and is never sent to the browser, and no CORS setup is needed since the browser never talks to FastAPI directly.

**Tech Stack:** FastAPI + httpx + SQLAlchemy 2.0 + APScheduler + pytest/respx (backend); Next.js 14 (App Router) + TypeScript + Tailwind + recharts + Vitest/Testing Library (frontend); SQLite for local dev, Postgres (Supabase) in production.

---

## Setup / conventions

- Backend commands assume your working directory is `backend/`; run tests with `python -m pytest ...` (not bare `pytest`) so the current directory is reliably on `sys.path` and `app` resolves as a package.
- Frontend commands assume your working directory is `frontend/`.
- Prerequisites: Python 3.11+, Node 18.17+, and a Trading212 API key pair generated in the Trading212 app (Settings → API, Beta) scoped to **read-only account data, portfolio, and history** — never grant order-placement permission, since this app must never place trades.
- No migration tool (Alembic) is introduced in this phase — `Base.metadata.create_all()` is sufficient for one table. Add Alembic when schema changes need to be versioned across environments (phase 2+).
- Trading212 API facts this plan relies on (verified against `docs.trading212.com/api` during planning):
  - Base URL: `https://live.trading212.com/api/v0` (paper/demo: `https://demo.trading212.com/api/v0`)
  - Auth: `Authorization: Basic <base64(api_key:api_secret)>`
  - `GET /equity/account/summary` → `{ id, currency, totalValue, cash: { availableToTrade, inPies, reservedForOrders }, investments: { currentValue, totalCost, unrealizedProfitLoss, realizedProfitLoss } }`
  - `GET /equity/positions` → list of `{ instrument: { ticker, name, isin, currency }, quantity, averagePricePaid, currentPrice, quantityAvailableForTrading, quantityInPies, createdAt, walletImpact: { currency, currentValue, fxImpact, totalCost, unrealizedProfitLoss } }`
  - This is a beta API — exact rate limits for these two endpoints weren't published; the snapshot job defaults to a conservative 15-minute interval (configurable).

---

### Task 1: Backend scaffold + health check

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`
- Create: `.gitignore`

- [ ] **Step 1: Create the backend dependency files**

`backend/requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.32
httpx>=0.27
sqlalchemy>=2.0
psycopg2-binary>=2.9
pydantic-settings>=2.5
apscheduler>=3.10
```

`backend/requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.3
respx>=0.21
```

- [ ] **Step 2: Create the repo-wide `.gitignore`**

`.gitignore`:
```
# Python
__pycache__/
*.pyc
.venv/
*.db

# Node
node_modules/
.next/

# Env files
.env
.env.local

# OS
.DS_Store
```

- [ ] **Step 3: Create `backend/app/__init__.py`** (empty file, makes `app` an importable package)

- [ ] **Step 4: Write the failing test**

`backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Set up a virtualenv and install dependencies, then run the test to verify it fails**

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements-dev.txt
python -m pytest tests/test_health.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 6: Write the minimal implementation**

`backend/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="Trader API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Run the test to verify it passes**

```bash
python -m pytest tests/test_health.py -v
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/app/__init__.py backend/app/main.py backend/tests/test_health.py .gitignore
git commit -m "feat: scaffold FastAPI backend with health check"
```

---

### Task 2: Settings / configuration

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_config.py`:
```python
import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_requires_trading212_and_dashboard_credentials(monkeypatch):
    monkeypatch.delenv("TRADING212_API_KEY", raising=False)
    monkeypatch.delenv("TRADING212_API_SECRET", raising=False)
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_loads_from_environment_with_defaults(monkeypatch):
    monkeypatch.setenv("TRADING212_API_KEY", "key")
    monkeypatch.setenv("TRADING212_API_SECRET", "secret")
    monkeypatch.setenv("DASHBOARD_API_KEY", "dashboard-secret")

    settings = Settings(_env_file=None)

    assert settings.trading212_api_key == "key"
    assert settings.trading212_api_secret == "secret"
    assert settings.dashboard_api_key == "dashboard-secret"
    assert settings.trading212_base_url == "https://live.trading212.com/api/v0"
    assert settings.database_url == "sqlite:///./dev.db"
    assert settings.snapshot_interval_minutes == 15
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_config.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Write the minimal implementation**

`backend/app/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    trading212_api_key: str
    trading212_api_secret: str
    trading212_base_url: str = "https://live.trading212.com/api/v0"
    database_url: str = "sqlite:///./dev.db"
    dashboard_api_key: str
    snapshot_interval_minutes: int = 15


settings = Settings()
```

- [ ] **Step 4: Create a local `.env` from the example so `settings = Settings()` can instantiate**

`backend/.env.example`:
```
TRADING212_API_KEY=your-trading212-api-key
TRADING212_API_SECRET=your-trading212-api-secret
TRADING212_BASE_URL=https://live.trading212.com/api/v0
DATABASE_URL=sqlite:///./dev.db
DASHBOARD_API_KEY=choose-a-long-random-string
SNAPSHOT_INTERVAL_MINUTES=15
```

Copy it: `cp .env.example .env` and fill in your real Trading212 API key/secret and a random `DASHBOARD_API_KEY`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py backend/.env.example
git commit -m "feat: add environment-based settings"
```

---

### Task 3: Trading212 API client

**Files:**
- Create: `backend/app/trading212.py`
- Create: `backend/tests/test_trading212_client.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_trading212_client.py`:
```python
import base64

import httpx
import pytest
import respx

from app.trading212 import Trading212Client

BASE_URL = "https://live.trading212.com/api/v0"


@respx.mock
def test_get_account_summary_sends_basic_auth_and_returns_json():
    route = respx.get(f"{BASE_URL}/equity/account/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 12345,
                "currency": "USD",
                "totalValue": 10250.50,
                "cash": {"availableToTrade": 500.0, "inPies": 0.0, "reservedForOrders": 0.0},
                "investments": {
                    "currentValue": 9750.50,
                    "totalCost": 9000.0,
                    "unrealizedProfitLoss": 750.50,
                    "realizedProfitLoss": 120.0,
                },
            },
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    summary = client.get_account_summary()

    assert route.called
    assert summary["totalValue"] == 10250.50
    expected_auth = "Basic " + base64.b64encode(b"key:secret").decode()
    assert route.calls[0].request.headers["authorization"] == expected_auth


@respx.mock
def test_get_positions_returns_list_of_positions():
    respx.get(f"{BASE_URL}/equity/positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "instrument": {
                        "ticker": "NVDA_US_EQ",
                        "name": "NVIDIA Corp",
                        "isin": "US67066G1040",
                        "currency": "USD",
                    },
                    "quantity": 10.0,
                    "averagePricePaid": 120.5,
                    "currentPrice": 135.2,
                    "quantityAvailableForTrading": 10.0,
                    "quantityInPies": 0.0,
                    "createdAt": "2026-01-15T09:30:00Z",
                    "walletImpact": {
                        "currency": "USD",
                        "currentValue": 1352.0,
                        "fxImpact": 0.0,
                        "totalCost": 1205.0,
                        "unrealizedProfitLoss": 147.0,
                    },
                }
            ],
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    positions = client.get_positions()

    assert len(positions) == 1
    assert positions[0]["instrument"]["ticker"] == "NVDA_US_EQ"


@respx.mock
def test_raises_for_non_200_response():
    respx.get(f"{BASE_URL}/equity/account/summary").mock(return_value=httpx.Response(401))
    client = Trading212Client(api_key="bad", api_secret="bad", base_url=BASE_URL)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.get_account_summary()

    assert exc_info.value.response.status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_trading212_client.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.trading212'`

- [ ] **Step 3: Write the minimal implementation**

`backend/app/trading212.py`:
```python
import base64

import httpx


class Trading212Client:
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Basic {credentials}"},
            timeout=10.0,
        )

    def get_account_summary(self) -> dict:
        response = self._client.get("/equity/account/summary")
        response.raise_for_status()
        return response.json()

    def get_positions(self) -> list[dict]:
        response = self._client.get("/equity/positions")
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_trading212_client.py -v
```
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/trading212.py backend/tests/test_trading212_client.py
git commit -m "feat: add Trading212 API client"
```

---

### Task 4: Database models + snapshot storage

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: Write `backend/app/db.py`** (no test — this is engine/session plumbing, exercised indirectly by every DB test that follows)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

- [ ] **Step 2: Write the shared test fixtures**

`backend/tests/conftest.py`:
```python
import os

os.environ.setdefault("TRADING212_API_KEY", "test-api-key")
os.environ.setdefault("TRADING212_API_SECRET", "test-api-secret")
os.environ.setdefault("DASHBOARD_API_KEY", "test-dashboard-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 3: Write the failing test for the model**

`backend/tests/test_models.py`:
```python
from app.models import PortfolioSnapshot


def test_portfolio_snapshot_persists_with_defaults(db_session):
    snapshot = PortfolioSnapshot(total_value=10250.50, unrealized_profit_loss=750.50, currency="USD")

    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)

    assert snapshot.id is not None
    assert snapshot.taken_at is not None
    assert snapshot.total_value == 10250.50
    assert snapshot.currency == "USD"
```

- [ ] **Step 4: Run the test to verify it fails**

```bash
python -m pytest tests/test_models.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 5: Write the minimal implementation**

`backend/app/models.py`:
```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    total_value: Mapped[float] = mapped_column(Float)
    unrealized_profit_loss: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
```

- [ ] **Step 6: Run the test to verify it passes**

```bash
python -m pytest tests/test_models.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/db.py backend/app/models.py backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat: add PortfolioSnapshot model and DB session plumbing"
```

---

### Task 5: Snapshot service

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/snapshot.py`
- Create: `backend/tests/test_snapshot_service.py`

- [ ] **Step 1: Create `backend/app/services/__init__.py`** (empty file)

- [ ] **Step 2: Write the failing test**

`backend/tests/test_snapshot_service.py`:
```python
from unittest.mock import MagicMock

from app.models import PortfolioSnapshot
from app.services.snapshot import take_snapshot


def test_take_snapshot_persists_totals_from_the_client(db_session):
    fake_client = MagicMock()
    fake_client.get_account_summary.return_value = {
        "currency": "USD",
        "totalValue": 10250.50,
        "investments": {"unrealizedProfitLoss": 750.50},
    }

    snapshot = take_snapshot(db_session, fake_client)

    assert snapshot.id is not None
    stored = db_session.query(PortfolioSnapshot).all()
    assert len(stored) == 1
    assert stored[0].total_value == 10250.50
    assert stored[0].unrealized_profit_loss == 750.50
    assert stored[0].currency == "USD"
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
python -m pytest tests/test_snapshot_service.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.snapshot'`

- [ ] **Step 4: Write the minimal implementation**

`backend/app/services/snapshot.py`:
```python
from sqlalchemy.orm import Session

from ..models import PortfolioSnapshot
from ..trading212 import Trading212Client


def take_snapshot(session: Session, client: Trading212Client) -> PortfolioSnapshot:
    summary = client.get_account_summary()
    snapshot = PortfolioSnapshot(
        total_value=summary["totalValue"],
        unrealized_profit_loss=summary["investments"]["unrealizedProfitLoss"],
        currency=summary["currency"],
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
python -m pytest tests/test_snapshot_service.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/snapshot.py backend/tests/test_snapshot_service.py
git commit -m "feat: add snapshot service that persists Trading212 account totals"
```

---

### Task 6: Dashboard API-key auth dependency

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_auth.py`:
```python
import pytest
from fastapi import HTTPException

from app import config
from app.auth import require_api_key


def test_require_api_key_accepts_matching_bearer_token(monkeypatch):
    monkeypatch.setattr(config.settings, "dashboard_api_key", "expected-secret")

    require_api_key(authorization="Bearer expected-secret")  # should not raise


def test_require_api_key_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(config.settings, "dashboard_api_key", "expected-secret")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(authorization="Bearer wrong-secret")

    assert exc_info.value.status_code == 401


def test_require_api_key_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(config.settings, "dashboard_api_key", "expected-secret")

    with pytest.raises(HTTPException) as exc_info:
        require_api_key(authorization="")

    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_auth.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Write the minimal implementation**

`backend/app/auth.py`:
```python
from fastapi import Header, HTTPException

from .config import settings


def require_api_key(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.dashboard_api_key}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_auth.py -v
```
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat: add shared-secret auth dependency"
```

---

### Task 7: Portfolio router

**Files:**
- Create: `backend/app/dependencies.py`
- Create: `backend/app/schemas.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/portfolio.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_portfolio_router.py`

- [ ] **Step 1: Create `backend/app/routers/__init__.py`** (empty file)

- [ ] **Step 2: Write `backend/app/dependencies.py`**

```python
from typing import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from .db import SessionLocal
from .trading212 import Trading212Client


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_trading212_client(request: Request) -> Trading212Client:
    return request.app.state.trading212_client
```

- [ ] **Step 3: Write `backend/app/schemas.py`**

```python
from datetime import datetime

from pydantic import BaseModel


class CashBreakdown(BaseModel):
    availableToTrade: float
    inPies: float
    reservedForOrders: float


class AccountSummary(BaseModel):
    id: int
    currency: str
    totalValue: float
    cash: CashBreakdown
    unrealizedProfitLoss: float
    realizedProfitLoss: float


class Position(BaseModel):
    ticker: str
    name: str
    quantity: float
    averagePricePaid: float
    currentPrice: float
    currentValue: float
    unrealizedProfitLoss: float


class PortfolioCurrent(BaseModel):
    account: AccountSummary
    positions: list[Position]


class PortfolioSnapshotOut(BaseModel):
    takenAt: datetime
    totalValue: float
    unrealizedProfitLoss: float
```

- [ ] **Step 4: Extend the shared test fixtures with a `TestClient`**

Append to `backend/tests/conftest.py`:
```python

from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.main import app


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [ ] **Step 5: Write the failing tests for the router**

`backend/tests/test_portfolio_router.py`:
```python
from unittest.mock import MagicMock

from app.dependencies import get_trading212_client
from app.main import app
from app.models import PortfolioSnapshot

FAKE_SUMMARY = {
    "id": 1,
    "currency": "USD",
    "totalValue": 10250.50,
    "cash": {"availableToTrade": 500.0, "inPies": 0.0, "reservedForOrders": 0.0},
    "investments": {
        "currentValue": 9750.50,
        "totalCost": 9000.0,
        "unrealizedProfitLoss": 750.50,
        "realizedProfitLoss": 120.0,
    },
}
FAKE_POSITIONS = [
    {
        "instrument": {"ticker": "NVDA_US_EQ", "name": "NVIDIA Corp", "isin": "US1", "currency": "USD"},
        "quantity": 10.0,
        "averagePricePaid": 120.5,
        "currentPrice": 135.2,
        "walletImpact": {
            "currency": "USD",
            "currentValue": 1352.0,
            "fxImpact": 0.0,
            "totalCost": 1205.0,
            "unrealizedProfitLoss": 147.0,
        },
    }
]
AUTH_HEADER = {"Authorization": "Bearer test-dashboard-key"}


def test_get_current_portfolio_returns_account_and_positions(client):
    fake_client = MagicMock()
    fake_client.get_account_summary.return_value = FAKE_SUMMARY
    fake_client.get_positions.return_value = FAKE_POSITIONS
    app.dependency_overrides[get_trading212_client] = lambda: fake_client

    response = client.get("/api/portfolio/current", headers=AUTH_HEADER)

    del app.dependency_overrides[get_trading212_client]
    assert response.status_code == 200
    body = response.json()
    assert body["account"]["totalValue"] == 10250.50
    assert body["positions"][0]["ticker"] == "NVDA_US_EQ"
    assert body["positions"][0]["unrealizedProfitLoss"] == 147.0


def test_get_current_portfolio_requires_auth(client):
    response = client.get("/api/portfolio/current")

    assert response.status_code == 401


def test_get_portfolio_history_returns_stored_snapshots(client, db_session):
    db_session.add(PortfolioSnapshot(total_value=100.0, unrealized_profit_loss=5.0, currency="USD"))
    db_session.commit()

    response = client.get("/api/portfolio/history", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["totalValue"] == 100.0
```

- [ ] **Step 6: Run the tests to verify they fail**

```bash
python -m pytest tests/test_portfolio_router.py -v
```
Expected: FAIL (`app.main` has no `app.state.trading212_client` / router not wired yet — the failure will be an `ImportError` or `AttributeError` until Task 8 wires `main.py`; that's expected, note it and continue to the implementation step below since this task and Task 8 are tightly coupled)

- [ ] **Step 7: Write the router implementation**

`backend/app/routers/portfolio.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..dependencies import get_db, get_trading212_client
from ..models import PortfolioSnapshot
from ..schemas import AccountSummary, CashBreakdown, PortfolioCurrent, PortfolioSnapshotOut, Position
from ..trading212 import Trading212Client

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/portfolio/current", response_model=PortfolioCurrent)
def get_current_portfolio(client: Trading212Client = Depends(get_trading212_client)) -> PortfolioCurrent:
    summary = client.get_account_summary()
    positions = client.get_positions()
    return PortfolioCurrent(
        account=AccountSummary(
            id=summary["id"],
            currency=summary["currency"],
            totalValue=summary["totalValue"],
            cash=CashBreakdown(**summary["cash"]),
            unrealizedProfitLoss=summary["investments"]["unrealizedProfitLoss"],
            realizedProfitLoss=summary["investments"]["realizedProfitLoss"],
        ),
        positions=[
            Position(
                ticker=p["instrument"]["ticker"],
                name=p["instrument"]["name"],
                quantity=p["quantity"],
                averagePricePaid=p["averagePricePaid"],
                currentPrice=p["currentPrice"],
                currentValue=p["walletImpact"]["currentValue"],
                unrealizedProfitLoss=p["walletImpact"]["unrealizedProfitLoss"],
            )
            for p in positions
        ],
    )


@router.get("/portfolio/history", response_model=list[PortfolioSnapshotOut])
def get_portfolio_history(db: Session = Depends(get_db)) -> list[PortfolioSnapshotOut]:
    rows = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.taken_at).all()
    return [
        PortfolioSnapshotOut(
            takenAt=row.taken_at,
            totalValue=row.total_value,
            unrealizedProfitLoss=row.unrealized_profit_loss,
        )
        for row in rows
    ]
```

- [ ] **Step 8: Proceed to Task 8 to wire `main.py`, then return here and run**

```bash
python -m pytest tests/test_portfolio_router.py -v
```
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add backend/app/dependencies.py backend/app/schemas.py backend/app/routers/__init__.py backend/app/routers/portfolio.py backend/tests/conftest.py backend/tests/test_portfolio_router.py
git commit -m "feat: add portfolio router (current + history endpoints)"
```

---

### Task 8: Wire the app together (scheduler, lifespan, router) + Dockerfile

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/app/scheduler.py`
- Create: `backend/Dockerfile`

- [ ] **Step 1: Write `backend/app/scheduler.py`**

```python
from .config import settings
from .db import SessionLocal
from .services.snapshot import take_snapshot
from .trading212 import Trading212Client


def run_snapshot_job() -> None:
    client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
    )
    session = SessionLocal()
    try:
        take_snapshot(session, client)
    finally:
        session.close()
```

- [ ] **Step 2: Replace `backend/app/main.py` with the fully wired app**

```python
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from .config import settings
from .db import Base, engine
from .routers.portfolio import router as portfolio_router
from .scheduler import run_snapshot_job
from .trading212 import Trading212Client


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    app.state.trading212_client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
    )
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_snapshot_job, "interval", minutes=settings.snapshot_interval_minutes)
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Trader API", lifespan=lifespan)
app.include_router(portfolio_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 3: Run the full backend test suite**

```bash
python -m pytest -v
```
Expected: PASS — every test file from Tasks 1–7 passes now that `app.main` exposes `app.state.trading212_client` and the router is mounted.

- [ ] **Step 4: Manually verify the scheduler fires** — start the server and confirm a snapshot job is registered

```bash
uvicorn app.main:app --reload
```
In another terminal:
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`. Check the server startup logs — APScheduler logs a line noting the job was added with the configured interval. Stop the server with Ctrl+C once confirmed; a full end-to-end run against your real Trading212 account happens in Task 14.

- [ ] **Step 5: Write the Dockerfile for deployment**

`backend/Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/scheduler.py backend/Dockerfile
git commit -m "feat: wire scheduler and router into the FastAPI app, add Dockerfile"
```

---

### Task 9: Frontend scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.js`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/vitest.setup.ts`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/app/page.tsx`
- Create: `frontend/.env.local.example`

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "trader-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "vitest run"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "recharts": "^2.12.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "@types/node": "^20.16.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "vitest": "^2.1.0",
    "@vitejs/plugin-react": "^4.3.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.5.0",
    "jsdom": "^25.0.0"
  }
}
```

- [ ] **Step 2: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Write `frontend/next.config.js`**

```js
/** @type {import('next').NextConfig} */
const nextConfig = {};

module.exports = nextConfig;
```

- [ ] **Step 4: Write `frontend/tailwind.config.ts` and `frontend/postcss.config.js`**

`frontend/tailwind.config.ts`:
```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};

export default config;
```

`frontend/postcss.config.js`:
```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Write `frontend/vitest.config.ts` and `frontend/vitest.setup.ts`**

`frontend/vitest.config.ts`:
```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
  },
});
```

`frontend/vitest.setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 6: Write the app shell**

`frontend/app/globals.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`frontend/app/layout.tsx`:
```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trader Dashboard",
  description: "Swing trading portfolio dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

`frontend/app/page.tsx` (placeholder — replaced with the real dashboard in Task 13):
```tsx
export default function DashboardPage() {
  return <main className="p-8">Loading dashboard...</main>;
}
```

- [ ] **Step 7: Write `frontend/.env.local.example`**

```
BACKEND_URL=http://localhost:8000
DASHBOARD_API_KEY=choose-a-long-random-string
```
This must match the backend's `DASHBOARD_API_KEY` from `backend/.env`. Copy it: `cp .env.local.example .env.local` and fill in the matching value.

- [ ] **Step 8: Install dependencies and verify the scaffold builds**

```bash
cd frontend
npm install
npm run build
```
Expected: build succeeds and prints a route summary including `/`.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.js frontend/tailwind.config.ts frontend/postcss.config.js frontend/vitest.config.ts frontend/vitest.setup.ts frontend/app frontend/.env.local.example
git commit -m "feat: scaffold Next.js frontend"
```

---

### Task 10: Currency formatting + frontend API client

**Files:**
- Create: `frontend/lib/format.ts`
- Create: `frontend/lib/__tests__/format.test.ts`
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing test for currency formatting**

`frontend/lib/__tests__/format.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../format";

describe("formatCurrency", () => {
  it("matches Intl.NumberFormat output for the given currency", () => {
    const expected = new Intl.NumberFormat("en-GB", { style: "currency", currency: "USD" }).format(1352);
    expect(formatCurrency(1352, "USD")).toBe(expected);
  });

  it("rounds to two decimal places", () => {
    expect(formatCurrency(1352, "USD")).toContain("1,352.00");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npm run test -- lib/__tests__/format.test.ts
```
Expected: FAIL — `Cannot find module '../format'`

- [ ] **Step 3: Write the minimal implementation**

`frontend/lib/format.ts`:
```ts
export function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(value);
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
npm run test -- lib/__tests__/format.test.ts
```
Expected: PASS

- [ ] **Step 5: Write the shared types matching the backend's Pydantic schemas**

`frontend/lib/types.ts`:
```ts
export interface CashBreakdown {
  availableToTrade: number;
  inPies: number;
  reservedForOrders: number;
}

export interface AccountSummary {
  id: number;
  currency: string;
  totalValue: number;
  cash: CashBreakdown;
  unrealizedProfitLoss: number;
  realizedProfitLoss: number;
}

export interface Position {
  ticker: string;
  name: string;
  quantity: number;
  averagePricePaid: number;
  currentPrice: number;
  currentValue: number;
  unrealizedProfitLoss: number;
}

export interface PortfolioCurrent {
  account: AccountSummary;
  positions: Position[];
}

export interface PortfolioSnapshot {
  takenAt: string;
  totalValue: number;
  unrealizedProfitLoss: number;
}
```

- [ ] **Step 6: Write the failing tests for the API client**

`frontend/lib/__tests__/api.test.ts`:
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getPortfolioCurrent, getPortfolioHistory } from "../api";

describe("portfolio API client", () => {
  beforeEach(() => {
    process.env.BACKEND_URL = "https://backend.example.com";
    process.env.DASHBOARD_API_KEY = "test-key";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("fetches current portfolio from the backend with the bearer token", async () => {
    const mockResponse = {
      account: {
        id: 1,
        currency: "USD",
        totalValue: 100,
        cash: { availableToTrade: 0, inPies: 0, reservedForOrders: 0 },
        unrealizedProfitLoss: 0,
        realizedProfitLoss: 0,
      },
      positions: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getPortfolioCurrent();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.com/api/portfolio/current",
      expect.objectContaining({ headers: { Authorization: "Bearer test-key" } })
    );
    expect(result).toEqual(mockResponse);
  });

  it("throws when the backend responds with an error status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    );

    await expect(getPortfolioCurrent()).rejects.toThrow("Failed to fetch current portfolio: 500");
  });

  it("fetches portfolio history from the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    await getPortfolioHistory();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.com/api/portfolio/history",
      expect.objectContaining({ headers: { Authorization: "Bearer test-key" } })
    );
  });
});
```

- [ ] **Step 7: Run the tests to verify they fail**

```bash
npm run test -- lib/__tests__/api.test.ts
```
Expected: FAIL — `Cannot find module '../api'`

- [ ] **Step 8: Write the minimal implementation**

`frontend/lib/api.ts`:
```ts
import type { PortfolioCurrent, PortfolioSnapshot } from "./types";

function backendUrl(path: string): string {
  const base = process.env.BACKEND_URL;
  if (!base) {
    throw new Error("BACKEND_URL environment variable is not set");
  }
  return `${base}${path}`;
}

function authHeaders(): HeadersInit {
  const apiKey = process.env.DASHBOARD_API_KEY;
  if (!apiKey) {
    throw new Error("DASHBOARD_API_KEY environment variable is not set");
  }
  return { Authorization: `Bearer ${apiKey}` };
}

export async function getPortfolioCurrent(): Promise<PortfolioCurrent> {
  const response = await fetch(backendUrl("/api/portfolio/current"), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch current portfolio: ${response.status}`);
  }
  return response.json();
}

export async function getPortfolioHistory(): Promise<PortfolioSnapshot[]> {
  const response = await fetch(backendUrl("/api/portfolio/history"), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio history: ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 9: Run the tests to verify they pass**

```bash
npm run test -- lib/__tests__
```
Expected: PASS (5 passed)

- [ ] **Step 10: Commit**

```bash
git add frontend/lib
git commit -m "feat: add currency formatting helper and backend API client"
```

---

### Task 11: PortfolioSummary + PositionsTable components

**Files:**
- Create: `frontend/components/PortfolioSummary.tsx`
- Create: `frontend/components/__tests__/PortfolioSummary.test.tsx`
- Create: `frontend/components/PositionsTable.tsx`
- Create: `frontend/components/__tests__/PositionsTable.test.tsx`

- [ ] **Step 1: Write the failing test for `PortfolioSummary`**

`frontend/components/__tests__/PortfolioSummary.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { PortfolioSummary } from "../PortfolioSummary";

describe("PortfolioSummary", () => {
  it("renders total value, cash, and unrealized P/L", () => {
    render(
      <PortfolioSummary
        account={{
          id: 1,
          currency: "USD",
          totalValue: 10250.5,
          cash: { availableToTrade: 500, inPies: 0, reservedForOrders: 0 },
          unrealizedProfitLoss: 750.5,
          realizedProfitLoss: 120,
        }}
      />
    );

    expect(screen.getByText(formatCurrency(10250.5, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(500, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(750.5, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(120, "USD"))).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npm run test -- components/__tests__/PortfolioSummary.test.tsx
```
Expected: FAIL — `Cannot find module '../PortfolioSummary'`

- [ ] **Step 3: Write the minimal implementation**

`frontend/components/PortfolioSummary.tsx`:
```tsx
import { formatCurrency } from "../lib/format";
import type { AccountSummary } from "../lib/types";

export function PortfolioSummary({ account }: { account: AccountSummary }) {
  const isProfit = account.unrealizedProfitLoss >= 0;
  return (
    <div className="grid grid-cols-2 gap-4 rounded-lg border border-neutral-200 p-6 sm:grid-cols-4">
      <div>
        <p className="text-sm text-neutral-500">Total value</p>
        <p className="text-2xl font-semibold">{formatCurrency(account.totalValue, account.currency)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Cash available</p>
        <p className="text-2xl font-semibold">
          {formatCurrency(account.cash.availableToTrade, account.currency)}
        </p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Unrealized P/L</p>
        <p className={`text-2xl font-semibold ${isProfit ? "text-green-600" : "text-red-600"}`}>
          {formatCurrency(account.unrealizedProfitLoss, account.currency)}
        </p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Realized P/L</p>
        <p className="text-2xl font-semibold">{formatCurrency(account.realizedProfitLoss, account.currency)}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
npm run test -- components/__tests__/PortfolioSummary.test.tsx
```
Expected: PASS

- [ ] **Step 5: Write the failing tests for `PositionsTable`**

`frontend/components/__tests__/PositionsTable.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { PositionsTable } from "../PositionsTable";

describe("PositionsTable", () => {
  it("renders a row per position", () => {
    render(
      <PositionsTable
        currency="USD"
        positions={[
          {
            ticker: "NVDA_US_EQ",
            name: "NVIDIA Corp",
            quantity: 10,
            averagePricePaid: 120.5,
            currentPrice: 135.2,
            currentValue: 1352,
            unrealizedProfitLoss: 147,
          },
        ]}
      />
    );

    expect(screen.getByText("NVDA_US_EQ")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(135.2, "USD"))).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(147, "USD"))).toBeInTheDocument();
  });

  it("renders an empty state when there are no positions", () => {
    render(<PositionsTable currency="USD" positions={[]} />);

    expect(screen.getByText("No open positions.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run the tests to verify they fail**

```bash
npm run test -- components/__tests__/PositionsTable.test.tsx
```
Expected: FAIL — `Cannot find module '../PositionsTable'`

- [ ] **Step 7: Write the minimal implementation**

`frontend/components/PositionsTable.tsx`:
```tsx
import { formatCurrency } from "../lib/format";
import type { Position } from "../lib/types";

export function PositionsTable({ positions, currency }: { positions: Position[]; currency: string }) {
  if (positions.length === 0) {
    return <p className="text-neutral-500">No open positions.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500">
          <th className="py-2">Ticker</th>
          <th className="py-2">Quantity</th>
          <th className="py-2">Avg. price</th>
          <th className="py-2">Current price</th>
          <th className="py-2">Value</th>
          <th className="py-2">P/L</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((position) => (
          <tr key={position.ticker} className="border-b border-neutral-100">
            <td className="py-2 font-medium">{position.ticker}</td>
            <td className="py-2">{position.quantity}</td>
            <td className="py-2">{formatCurrency(position.averagePricePaid, currency)}</td>
            <td className="py-2">{formatCurrency(position.currentPrice, currency)}</td>
            <td className="py-2">{formatCurrency(position.currentValue, currency)}</td>
            <td className={`py-2 ${position.unrealizedProfitLoss >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(position.unrealizedProfitLoss, currency)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
npm run test -- components/__tests__
```
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add frontend/components/PortfolioSummary.tsx frontend/components/PositionsTable.tsx frontend/components/__tests__
git commit -m "feat: add PortfolioSummary and PositionsTable components"
```

---

### Task 12: EquityCurveChart component

**Files:**
- Create: `frontend/components/EquityCurveChart.tsx`
- Create: `frontend/components/__tests__/EquityCurveChart.test.tsx`

- [ ] **Step 1: Write the failing tests**

`frontend/components/__tests__/EquityCurveChart.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EquityCurveChart } from "../EquityCurveChart";

describe("EquityCurveChart", () => {
  it("shows an empty state when there is no history yet", () => {
    render(<EquityCurveChart snapshots={[]} />);

    expect(screen.getByText(/not enough history yet/i)).toBeInTheDocument();
  });

  it("renders a chart container when given snapshot data", () => {
    render(
      <EquityCurveChart
        snapshots={[
          { takenAt: "2026-09-01T00:00:00Z", totalValue: 10000, unrealizedProfitLoss: 100 },
          { takenAt: "2026-09-02T00:00:00Z", totalValue: 10200, unrealizedProfitLoss: 300 },
        ]}
      />
    );

    expect(document.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
npm run test -- components/__tests__/EquityCurveChart.test.tsx
```
Expected: FAIL — `Cannot find module '../EquityCurveChart'`

- [ ] **Step 3: Write the minimal implementation**

`frontend/components/EquityCurveChart.tsx`:
```tsx
"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PortfolioSnapshot } from "../lib/types";

export function EquityCurveChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  if (snapshots.length === 0) {
    return <p className="text-neutral-500">Not enough history yet — check back after the next snapshot.</p>;
  }
  const data = snapshots.map((snapshot) => ({
    date: new Date(snapshot.takenAt).toLocaleDateString(),
    value: snapshot.totalValue,
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <XAxis dataKey="date" />
        <YAxis domain={["auto", "auto"]} />
        <Tooltip />
        <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm run test -- components/__tests__/EquityCurveChart.test.tsx
```
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/EquityCurveChart.tsx frontend/components/__tests__/EquityCurveChart.test.tsx
git commit -m "feat: add EquityCurveChart component"
```

---

### Task 13: Wire the real dashboard page

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Replace the placeholder page with the real dashboard**

`frontend/app/page.tsx`:
```tsx
import { EquityCurveChart } from "../components/EquityCurveChart";
import { PortfolioSummary } from "../components/PortfolioSummary";
import { PositionsTable } from "../components/PositionsTable";
import { getPortfolioCurrent, getPortfolioHistory } from "../lib/api";

export default async function DashboardPage() {
  const [current, history] = await Promise.all([getPortfolioCurrent(), getPortfolioHistory()]);

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <h1 className="text-3xl font-bold">Portfolio dashboard</h1>
      <PortfolioSummary account={current.account} />
      <section>
        <h2 className="mb-4 text-xl font-semibold">Value over time</h2>
        <EquityCurveChart snapshots={history} />
      </section>
      <section>
        <h2 className="mb-4 text-xl font-semibold">Open positions</h2>
        <PositionsTable positions={current.positions} currency={current.account.currency} />
      </section>
    </main>
  );
}
```

- [ ] **Step 2: Run the full frontend test suite and the build**

```bash
npm run test
npm run build
```
Expected: all tests pass; the build succeeds (type errors in `page.tsx` would fail the build, so this doubles as a type-check of the wiring since there's no separate unit test for this Server Component).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: wire the dashboard page to the backend API"
```

---

### Task 14: End-to-end verification, deployment, and doc update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run both apps locally against your real Trading212 account**

Backend (in `backend/`, with `.env` filled in with your real Trading212 API key/secret and a chosen `DASHBOARD_API_KEY`):
```bash
uvicorn app.main:app --reload
```

Frontend (in `frontend/`, with `.env.local` filled in with `BACKEND_URL=http://localhost:8000` and the same `DASHBOARD_API_KEY`):
```bash
npm run dev
```

Open `http://localhost:3000` in a browser. Expected: the dashboard renders your real total portfolio value, cash available, unrealized/realized P/L, and a table of your actual open Trading212 positions. The equity-curve section will show the empty state until the scheduler has taken at least one snapshot (wait for the configured `SNAPSHOT_INTERVAL_MINUTES`, or temporarily set it to `1` in `backend/.env` to verify faster, then restart the backend).

- [ ] **Step 2: Confirm the auth boundary works**

```bash
curl -i http://localhost:8000/api/portfolio/current
```
Expected: `401 Unauthorized` (no `Authorization` header). Then:
```bash
curl -i http://localhost:8000/api/portfolio/current -H "Authorization: Bearer <your DASHBOARD_API_KEY>"
```
Expected: `200 OK` with your portfolio JSON.

- [ ] **Step 3: Deploy the backend to Railway (or Render)**

Create a new project from the `backend/` directory (Railway/Render both auto-detect the `Dockerfile`). Set these environment variables in the platform's dashboard: `TRADING212_API_KEY`, `TRADING212_API_SECRET`, `TRADING212_BASE_URL`, `DASHBOARD_API_KEY`, `SNAPSHOT_INTERVAL_MINUTES`, and `DATABASE_URL` pointing at a Supabase Postgres connection string (create a free Supabase project, copy its connection string from Project Settings → Database). Note the deployed backend's public URL.

- [ ] **Step 4: Deploy the frontend to Vercel**

Import the repo into Vercel, set the project root to `frontend/`. Set environment variables `BACKEND_URL` (the Railway/Render URL from Step 3) and `DASHBOARD_API_KEY` (same value as the backend) — leave them **without** the `NEXT_PUBLIC_` prefix so they stay server-side only. Deploy, then open the Vercel URL and confirm the dashboard renders the same data as local.

- [ ] **Step 5: Update `CLAUDE.md` with the now-real commands and structure**

In `CLAUDE.md`, replace the "Project status" section's claim that there are no build/lint/test commands with:

```markdown
## Commands

Backend (run from `backend/`, with a virtualenv activated):
- Install deps: `pip install -r requirements-dev.txt`
- Run tests: `python -m pytest -v`
- Run a single test: `python -m pytest tests/test_portfolio_router.py::test_get_current_portfolio_returns_account_and_positions -v`
- Run dev server: `uvicorn app.main:app --reload`

Frontend (run from `frontend/`):
- Install deps: `npm install`
- Run tests: `npm run test`
- Run dev server: `npm run dev`
- Build: `npm run build`
```

Also update the "Intended architecture" section to say this phase 1 architecture is now implemented, and briefly describe the actual repo layout (`backend/app/` — client, models, services, routers; `frontend/app/`, `frontend/components/`, `frontend/lib/`).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with real commands after phase 1"
```
