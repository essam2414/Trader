# Trade Performance Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync Trading212 order/dividend history into new local tables, compute trade performance metrics (realized P&L, win rate, expectancy, profit factor, drawdown, and more) from them, and surface those metrics as a new "Performance" section on the existing dashboard.

**Architecture:** A scheduled sync job pulls raw order fills and dividends from two new Trading212 API endpoints into two new DB tables (idempotent upsert). A pure, I/O-free `metrics.py` module reconstructs discrete closed trades from those fills via FIFO lot matching and computes every metric from them plus the existing `portfolio_snapshots` table. A new `GET /api/portfolio/metrics` endpoint assembles the computed metrics (plus a live cash-drag figure from the account summary) into one response, which a new frontend section renders as a stats grid and a by-ticker table.

**Tech Stack:** FastAPI, SQLAlchemy, httpx/respx (backend); Next.js 14, TypeScript, Vitest/Testing Library (frontend) — same stack as the rest of the app, no new dependencies.

**Design doc:** `docs/superpowers/specs/2026-09-19-trade-performance-metrics-design.md`

---

## Task 1: `OrderFill` and `Dividend` ORM models

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `backend/tests/test_models.py`:

```python
def test_order_fill_persists_with_all_fields(db_session):
    """An OrderFill should persist every synced field from a Trading212 fill."""
    from datetime import datetime, timezone

    from app.models import OrderFill

    fill = OrderFill(
        id="101",
        order_id="1",
        ticker="AAPL_US_EQ",
        side="BUY",
        quantity=10.0,
        fill_price=100.0,
        net_value=1000.0,
        realised_profit_loss=0.0,
        fees=1.0,
        currency="USD",
        filled_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
    )

    db_session.add(fill)
    db_session.commit()
    db_session.refresh(fill)

    assert fill.id == "101"
    assert fill.side == "BUY"
    assert fill.fees == 1.0


def test_dividend_persists_with_all_fields(db_session):
    """A Dividend should persist every synced field from a Trading212 dividend payment."""
    from datetime import datetime, timezone

    from app.models import Dividend

    dividend = Dividend(
        id="div-ref-1",
        ticker="AAPL_US_EQ",
        amount=5.0,
        currency="USD",
        type="ORDINARY",
        paid_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )

    db_session.add(dividend)
    db_session.commit()
    db_session.refresh(dividend)

    assert dividend.id == "div-ref-1"
    assert dividend.amount == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`, venv activated): `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'OrderFill' from 'app.models'`

- [ ] **Step 3: Add the models**

Append to `backend/app/models.py`:

```python
class OrderFill(Base):
    """A single executed buy/sell fill, synced from Trading212's order history.

    Only fills of type "TRADE" are stored — corporate-action fills (stock
    splits, stock dividends, spin-offs, etc.) are filtered out during sync
    since they'd corrupt FIFO trade reconstruction if included.
    """

    __tablename__ = "order_fills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(String)
    ticker: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[float] = mapped_column(Float)
    fill_price: Mapped[float] = mapped_column(Float)
    net_value: Mapped[float] = mapped_column(Float)
    realised_profit_loss: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Dividend(Base):
    """A single dividend payment, synced from Trading212's dividend history."""

    __tablename__ = "dividends"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    type: Mapped[str] = mapped_column(String)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (4 tests: the 2 new plus the existing `PortfolioSnapshot` test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat: add OrderFill and Dividend models"
```

---

## Task 2: `Trading212Client` historical orders & dividends methods

**Files:**
- Modify: `backend/app/trading212.py`
- Test: `backend/tests/test_trading212_client.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `backend/tests/test_trading212_client.py`:

```python
@respx.mock
def test_get_historical_orders_returns_items_and_next_page_path():
    """get_historical_orders should return the parsed page (items + nextPagePath)."""
    respx.get(f"{BASE_URL}/equity/history/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"order": {"id": 1, "ticker": "AAPL_US_EQ"}, "fill": {"id": 101}}],
                "nextPagePath": "/api/v0/equity/history/orders?cursor=2&limit=50",
            },
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    page = client.get_historical_orders()

    assert page["items"][0]["fill"]["id"] == 101
    assert page["nextPagePath"] == "/api/v0/equity/history/orders?cursor=2&limit=50"


@respx.mock
def test_get_historical_orders_sends_cursor_as_query_param():
    """When given a cursor, get_historical_orders should send it as a query param."""
    route = respx.get(f"{BASE_URL}/equity/history/orders", params={"cursor": "2"}).mock(
        return_value=httpx.Response(200, json={"items": [], "nextPagePath": None})
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    client.get_historical_orders(cursor=2)

    assert route.called


@respx.mock
def test_get_historical_orders_omits_cursor_param_on_first_page():
    """With no cursor given, the request should not include a cursor query param at all."""
    respx.get(f"{BASE_URL}/equity/history/orders").mock(
        return_value=httpx.Response(200, json={"items": [], "nextPagePath": None})
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    client.get_historical_orders()

    request = respx.calls[-1].request
    assert "cursor" not in request.url.params


@respx.mock
def test_get_dividends_returns_items_and_next_page_path():
    """get_dividends should return the parsed page (items + nextPagePath)."""
    respx.get(f"{BASE_URL}/equity/history/dividends").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"ticker": "AAPL_US_EQ", "amount": 5.0}],
                "nextPagePath": None,
            },
        )
    )
    client = Trading212Client(api_key="key", api_secret="secret", base_url=BASE_URL)

    page = client.get_dividends()

    assert page["items"][0]["ticker"] == "AAPL_US_EQ"
    assert page["nextPagePath"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trading212_client.py -v`
Expected: FAIL with `AttributeError: 'Trading212Client' object has no attribute 'get_historical_orders'`

- [ ] **Step 3: Add the client methods**

Append to `backend/app/trading212.py` (inside the `Trading212Client` class, after `get_positions`):

```python
    def get_historical_orders(self, cursor: int | None = None, ticker: str | None = None) -> dict:
        """Retrieve one page of historical order/fill data.

        Args:
            cursor: Pagination cursor from a previous page's nextPagePath, or
                None to fetch the first page.
            ticker: Optional ticker to filter results to a single instrument.

        Returns:
            Dict with "items" (list of order/fill records) and "nextPagePath"
            (str or None) for the next page.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        params: dict[str, str | int] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if ticker is not None:
            params["ticker"] = ticker
        response = self._client.get("/equity/history/orders", params=params)
        response.raise_for_status()
        return response.json()

    def get_dividends(self, cursor: int | None = None, ticker: str | None = None) -> dict:
        """Retrieve one page of historical dividend payment data.

        Args:
            cursor: Pagination cursor from a previous page's nextPagePath, or
                None to fetch the first page.
            ticker: Optional ticker to filter results to a single instrument.

        Returns:
            Dict with "items" (list of dividend records) and "nextPagePath"
            (str or None) for the next page.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status code.
        """
        params: dict[str, str | int] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if ticker is not None:
            params["ticker"] = ticker
        response = self._client.get("/equity/history/dividends", params=params)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_trading212_client.py -v`
Expected: PASS (7 tests: the 4 new plus the existing 3)

- [ ] **Step 5: Commit**

```bash
git add backend/app/trading212.py backend/tests/test_trading212_client.py
git commit -m "feat: add Trading212Client methods for historical orders and dividends"
```

---

## Task 3: Metrics service — FIFO trade matching

**Files:**
- Create: `backend/app/services/metrics.py`
- Test: `backend/tests/test_metrics_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_metrics_service.py`:

```python
"""Tests for the trade metrics service (FIFO matching and aggregate calculations)."""

from datetime import datetime, timezone

import pytest

from app.models import OrderFill
from app.services.metrics import match_trades


def _fill(fill_id, ticker, side, quantity, price, filled_at, fees=0.0, realised_profit_loss=0.0):
    return OrderFill(
        id=fill_id,
        order_id=fill_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        fill_price=price,
        net_value=quantity * price,
        realised_profit_loss=realised_profit_loss,
        fees=fees,
        currency="USD",
        filled_at=filled_at,
    )


def test_match_trades_matches_fifo_across_partial_lots():
    """A sell spanning two buy lots should produce two closed trades, oldest lot first."""
    fills = [
        _fill("1", "AAPL_US_EQ", "BUY", 10.0, 100.0, datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _fill("2", "AAPL_US_EQ", "BUY", 5.0, 110.0, datetime(2026, 1, 2, tzinfo=timezone.utc)),
        _fill("3", "AAPL_US_EQ", "SELL", 12.0, 120.0, datetime(2026, 1, 3, tzinfo=timezone.utc)),
    ]

    trades = match_trades(fills)

    assert len(trades) == 2
    assert trades[0].quantity == 10.0
    assert trades[0].entry_price == 100.0
    assert trades[0].pnl == pytest.approx(200.0)
    assert trades[1].quantity == 2.0
    assert trades[1].entry_price == 110.0
    assert trades[1].pnl == pytest.approx(20.0)


def test_match_trades_accounts_for_entry_and_exit_fees():
    """FIFO P&L should subtract both the buy fill's and sell fill's fees, prorated by quantity."""
    fills = [
        _fill("1", "AAPL_US_EQ", "BUY", 10.0, 100.0, datetime(2026, 1, 1, tzinfo=timezone.utc), fees=1.0),
        _fill("2", "AAPL_US_EQ", "SELL", 10.0, 110.0, datetime(2026, 1, 5, tzinfo=timezone.utc), fees=1.0),
    ]

    trades = match_trades(fills)

    assert len(trades) == 1
    assert trades[0].pnl == pytest.approx(98.0)  # 10*(110-100) - 1 - 1
    assert trades[0].fees == pytest.approx(2.0)
    assert trades[0].holding_period.days == 4


def test_match_trades_ignores_unmatched_open_lots():
    """A buy with no corresponding sell yet shouldn't produce a closed trade."""
    fills = [_fill("1", "AAPL_US_EQ", "BUY", 10.0, 100.0, datetime(2026, 1, 1, tzinfo=timezone.utc))]

    assert match_trades(fills) == []


def test_match_trades_keeps_tickers_independent():
    """Fills for different tickers should never be matched against each other."""
    fills = [
        _fill("1", "AAPL_US_EQ", "BUY", 10.0, 100.0, datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _fill("2", "MSFT_US_EQ", "SELL", 10.0, 200.0, datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]

    assert match_trades(fills) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_metrics_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.metrics'`

- [ ] **Step 3: Implement FIFO matching**

Create `backend/app/services/metrics.py`:

```python
"""Trade performance metrics service.

Pure, I/O-free functions that reconstruct discrete closed trades from raw
Trading212 order fills (via FIFO lot matching) and compute performance
metrics from them. Kept free of DB/HTTP dependencies so every calculation
can be unit-tested against hand-built fixture data.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import Dividend, OrderFill, PortfolioSnapshot


@dataclass
class ClosedTrade:
    """A discrete closed trade reconstructed by matching a sell fill (or part
    of one) against the oldest still-open buy lot(s) for the same ticker."""

    ticker: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_at: datetime
    exit_at: datetime
    pnl: float
    fees: float

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def holding_period(self) -> timedelta:
        return self.exit_at - self.entry_at


def match_trades(fills: list[OrderFill]) -> list[ClosedTrade]:
    """Reconstruct discrete closed trades from raw fills using FIFO matching.

    Buys open lots; each sell consumes the oldest open lot(s) for that ticker
    first. A sell spanning multiple lots produces one ClosedTrade per lot
    consumed. Unmatched open buy lots (still-open positions) produce no
    trade. Fees are prorated to the matched quantity on both the entry (buy)
    and exit (sell) side.
    """
    fills_by_ticker: dict[str, list[OrderFill]] = defaultdict(list)
    for fill in fills:
        fills_by_ticker[fill.ticker].append(fill)

    trades: list[ClosedTrade] = []
    for ticker, ticker_fills in fills_by_ticker.items():
        open_lots: deque = deque()
        for fill in sorted(ticker_fills, key=lambda f: f.filled_at):
            if fill.side == "BUY":
                fee_per_unit = fill.fees / fill.quantity if fill.quantity else 0.0
                open_lots.append(
                    {
                        "quantity": fill.quantity,
                        "price": fill.fill_price,
                        "filled_at": fill.filled_at,
                        "fee_per_unit": fee_per_unit,
                    }
                )
            elif fill.side == "SELL":
                remaining = fill.quantity
                sell_fee_per_unit = fill.fees / fill.quantity if fill.quantity else 0.0
                while remaining > 1e-9 and open_lots:
                    lot = open_lots[0]
                    matched_qty = min(remaining, lot["quantity"])
                    entry_fees = matched_qty * lot["fee_per_unit"]
                    exit_fees = matched_qty * sell_fee_per_unit
                    pnl = matched_qty * (fill.fill_price - lot["price"]) - entry_fees - exit_fees
                    trades.append(
                        ClosedTrade(
                            ticker=ticker,
                            quantity=matched_qty,
                            entry_price=lot["price"],
                            exit_price=fill.fill_price,
                            entry_at=lot["filled_at"],
                            exit_at=fill.filled_at,
                            pnl=pnl,
                            fees=entry_fees + exit_fees,
                        )
                    )
                    lot["quantity"] -= matched_qty
                    remaining -= matched_qty
                    if lot["quantity"] <= 1e-9:
                        open_lots.popleft()

    trades.sort(key=lambda t: t.exit_at)
    return trades
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_metrics_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/metrics.py backend/tests/test_metrics_service.py
git commit -m "feat: add FIFO trade matching to the metrics service"
```

---

## Task 4: Metrics service — max drawdown

**Files:**
- Modify: `backend/app/services/metrics.py`
- Test: `backend/tests/test_metrics_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_metrics_service.py` (add `PortfolioSnapshot` to the existing `from app.models import ...` line, and `compute_max_drawdown` to the existing `from app.services.metrics import ...` line):

```python
def test_compute_max_drawdown_finds_largest_peak_to_trough_decline():
    snapshots = [
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc), total_value=1000.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 2, tzinfo=timezone.utc), total_value=1200.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 3, tzinfo=timezone.utc), total_value=900.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 4, tzinfo=timezone.utc), total_value=1100.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
    ]

    assert compute_max_drawdown(snapshots) == pytest.approx(0.25)


def test_compute_max_drawdown_is_zero_with_fewer_than_two_snapshots():
    assert compute_max_drawdown([]) == 0.0
    assert (
        compute_max_drawdown(
            [
                PortfolioSnapshot(
                    taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc), total_value=1000.0,
                    unrealized_profit_loss=0.0, currency="USD",
                )
            ]
        )
        == 0.0
    )
```

The top of `backend/tests/test_metrics_service.py` should now read:

```python
from app.models import OrderFill, PortfolioSnapshot
from app.services.metrics import compute_max_drawdown, match_trades
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_metrics_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_max_drawdown'`

- [ ] **Step 3: Implement drawdown**

Append to `backend/app/services/metrics.py`:

```python
def compute_max_drawdown(snapshots: list[PortfolioSnapshot]) -> float:
    """Largest peak-to-trough decline across the equity-curve snapshots, as a
    fraction of the peak (e.g. 0.25 = a 25% decline from the running high)."""
    if len(snapshots) < 2:
        return 0.0
    ordered = sorted(snapshots, key=lambda s: s.taken_at)
    peak = ordered[0].total_value
    max_drawdown = 0.0
    for snapshot in ordered:
        peak = max(peak, snapshot.total_value)
        if peak > 0:
            drawdown = (peak - snapshot.total_value) / peak
            max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_metrics_service.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/metrics.py backend/tests/test_metrics_service.py
git commit -m "feat: add max drawdown calculation to the metrics service"
```

---

## Task 5: Metrics service — aggregate portfolio metrics

**Files:**
- Modify: `backend/app/services/metrics.py`
- Test: `backend/tests/test_metrics_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_metrics_service.py` (update the top-of-file imports to add `Dividend` and `compute_portfolio_metrics`, see below):

```python
def test_compute_portfolio_metrics_aggregates_trades_dividends_and_drawdown():
    fills = [
        # AAPL: win. realised_profit_loss is set equal to the FIFO result here
        # deliberately, so this fixture doubles as a check that the two P&L
        # figures line up when there's no scaling in/out to cause divergence.
        _fill(
            "1", "AAPL_US_EQ", "BUY", 10.0, 100.0,
            datetime(2026, 1, 1, 10, tzinfo=timezone.utc), fees=1.0,
        ),
        _fill(
            "2", "AAPL_US_EQ", "SELL", 10.0, 110.0,
            datetime(2026, 1, 5, 10, tzinfo=timezone.utc), fees=1.0, realised_profit_loss=98.0,
        ),
        # MSFT: win
        _fill(
            "3", "MSFT_US_EQ", "BUY", 2.0, 200.0,
            datetime(2026, 1, 10, 12, tzinfo=timezone.utc),
        ),
        _fill(
            "4", "MSFT_US_EQ", "SELL", 2.0, 205.0,
            datetime(2026, 1, 11, 12, tzinfo=timezone.utc), realised_profit_loss=10.0,
        ),
        # AAPL: loss
        _fill(
            "5", "AAPL_US_EQ", "BUY", 5.0, 50.0,
            datetime(2026, 2, 1, 9, tzinfo=timezone.utc), fees=0.5,
        ),
        _fill(
            "6", "AAPL_US_EQ", "SELL", 5.0, 40.0,
            datetime(2026, 2, 3, 9, tzinfo=timezone.utc), fees=0.5, realised_profit_loss=-51.0,
        ),
    ]
    dividends = [
        Dividend(
            id="d1", ticker="AAPL_US_EQ", amount=5.0, currency="USD", type="ORDINARY",
            paid_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        ),
        Dividend(
            id="d2", ticker="AAPL_US_EQ", amount=3.0, currency="USD", type="ORDINARY",
            paid_at=datetime(2026, 1, 25, tzinfo=timezone.utc),
        ),
        Dividend(
            id="d3", ticker="MSFT_US_EQ", amount=2.0, currency="USD", type="ORDINARY",
            paid_at=datetime(2026, 1, 25, tzinfo=timezone.utc),
        ),
    ]
    snapshots = [
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc), total_value=1000.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 2, tzinfo=timezone.utc), total_value=1200.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 3, tzinfo=timezone.utc), total_value=900.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 4, tzinfo=timezone.utc), total_value=1100.0,
            unrealized_profit_loss=0.0, currency="USD",
        ),
    ]

    metrics = compute_portfolio_metrics(fills, dividends, snapshots)

    assert metrics.closed_trade_count == 3
    assert metrics.realized_pnl == pytest.approx(57.0)  # 98 + 10 - 51
    assert metrics.trading212_realized_pnl == pytest.approx(57.0)
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.average_winning_trade == pytest.approx(54.0)  # (98+10)/2
    assert metrics.average_losing_trade == pytest.approx(-51.0)
    assert metrics.expectancy == pytest.approx(19.0)
    assert metrics.profit_factor == pytest.approx(108 / 51)
    assert metrics.payoff_ratio == pytest.approx(54 / 51)
    assert metrics.average_holding_period_hours == pytest.approx(56.0)  # (96+24+48)/3
    assert metrics.best_trade_pnl == pytest.approx(98.0)
    assert metrics.worst_trade_pnl == pytest.approx(-51.0)
    assert metrics.current_streak == -1
    assert metrics.longest_win_streak == 2
    assert metrics.longest_loss_streak == 1
    assert metrics.max_drawdown == pytest.approx(0.25)
    assert metrics.dividend_income == pytest.approx(10.0)
    assert metrics.dividend_income_by_ticker == {"AAPL_US_EQ": 8.0, "MSFT_US_EQ": 2.0}

    by_ticker = {tp.ticker: tp for tp in metrics.performance_by_ticker}
    assert by_ticker["AAPL_US_EQ"].realized_pnl == pytest.approx(47.0)  # 98 - 51
    assert by_ticker["AAPL_US_EQ"].trade_count == 2
    assert by_ticker["AAPL_US_EQ"].win_rate == pytest.approx(0.5)
    assert by_ticker["MSFT_US_EQ"].realized_pnl == pytest.approx(10.0)
    assert by_ticker["MSFT_US_EQ"].trade_count == 1
    assert by_ticker["MSFT_US_EQ"].win_rate == pytest.approx(1.0)

    assert sum(metrics.entries_by_day_of_week.values()) == 3
    assert sum(metrics.exits_by_day_of_week.values()) == 3
    assert sum(metrics.entries_by_hour_of_day.values()) == 3
    assert sum(metrics.exits_by_hour_of_day.values()) == 3


def test_compute_portfolio_metrics_handles_no_closed_trades():
    metrics = compute_portfolio_metrics([], [], [])

    assert metrics.closed_trade_count == 0
    assert metrics.win_rate == 0.0
    assert metrics.profit_factor is None
    assert metrics.payoff_ratio is None
    assert metrics.best_trade_pnl is None
    assert metrics.worst_trade_pnl is None
    assert metrics.average_holding_period_hours == 0.0
    assert metrics.performance_by_ticker == []
    assert metrics.dividend_income == 0.0


def test_count_by_day_of_week_buckets_matching_weekdays_together():
    from app.services.metrics import _count_by_day_of_week

    # 2026-01-05 and 2026-01-12 fall on the same weekday (7 days apart);
    # 2026-01-01 is a different weekday (not a multiple of 7 days from either).
    result = _count_by_day_of_week(
        [
            datetime(2026, 1, 5, tzinfo=timezone.utc),
            datetime(2026, 1, 12, tzinfo=timezone.utc),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        ]
    )

    assert sum(result.values()) == 3
    assert max(result.values()) == 2


def test_count_by_hour_of_day_buckets_matching_hours_together():
    from app.services.metrics import _count_by_hour_of_day

    result = _count_by_hour_of_day(
        [
            datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
            datetime(2026, 1, 5, 9, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 14, tzinfo=timezone.utc),
        ]
    )

    assert result["9"] == 2
    assert result["14"] == 1
    assert sum(result.values()) == 3
```

Update the top of `backend/tests/test_metrics_service.py` to:

```python
from app.models import Dividend, OrderFill, PortfolioSnapshot
from app.services.metrics import compute_max_drawdown, compute_portfolio_metrics, match_trades
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_metrics_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_portfolio_metrics'`

- [ ] **Step 3: Implement the aggregate metrics**

Append to `backend/app/services/metrics.py`:

```python
@dataclass
class TickerPerformance:
    ticker: str
    realized_pnl: float
    trade_count: int
    win_rate: float


@dataclass
class PortfolioMetrics:
    realized_pnl: float
    trading212_realized_pnl: float
    win_rate: float
    average_winning_trade: float
    average_losing_trade: float
    expectancy: float
    profit_factor: float | None
    payoff_ratio: float | None
    average_holding_period_hours: float
    best_trade_pnl: float | None
    worst_trade_pnl: float | None
    current_streak: int
    longest_win_streak: int
    longest_loss_streak: int
    closed_trade_count: int
    performance_by_ticker: list[TickerPerformance]
    entries_by_day_of_week: dict[str, int]
    exits_by_day_of_week: dict[str, int]
    entries_by_hour_of_day: dict[str, int]
    exits_by_hour_of_day: dict[str, int]
    max_drawdown: float
    dividend_income: float
    dividend_income_by_ticker: dict[str, float]


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def compute_portfolio_metrics(
    fills: list[OrderFill],
    dividends: list[Dividend],
    snapshots: list[PortfolioSnapshot],
) -> PortfolioMetrics:
    """Compute every trade/dividend/drawdown performance metric from synced history.

    Does not include cash drag — that's a live, non-historical figure the API
    router adds separately from a fresh account-summary call.
    """
    trades = match_trades(fills)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    closed_trade_count = len(trades)
    win_rate = len(wins) / closed_trade_count if closed_trade_count else 0.0
    loss_rate = len(losses) / closed_trade_count if closed_trade_count else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = sum(-t.pnl for t in losses)
    average_winning_trade = gross_profit / len(wins) if wins else 0.0
    average_losing_trade = -(gross_loss / len(losses)) if losses else 0.0
    expectancy = (win_rate * average_winning_trade) + (loss_rate * average_losing_trade)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    payoff_ratio = (
        average_winning_trade / abs(average_losing_trade) if average_losing_trade != 0 else None
    )
    average_holding_period_hours = (
        sum(t.holding_period.total_seconds() for t in trades) / closed_trade_count / 3600
        if closed_trade_count
        else 0.0
    )
    best_trade_pnl = max((t.pnl for t in trades), default=None)
    worst_trade_pnl = min((t.pnl for t in trades), default=None)
    current_streak, longest_win_streak, longest_loss_streak = _compute_streaks(trades)

    trades_by_ticker: dict[str, list[ClosedTrade]] = defaultdict(list)
    for trade in trades:
        trades_by_ticker[trade.ticker].append(trade)
    performance_by_ticker = [
        TickerPerformance(
            ticker=ticker,
            realized_pnl=sum(t.pnl for t in ticker_trades),
            trade_count=len(ticker_trades),
            win_rate=sum(1 for t in ticker_trades if t.pnl > 0) / len(ticker_trades),
        )
        for ticker, ticker_trades in sorted(trades_by_ticker.items())
    ]

    dividend_income = sum(d.amount for d in dividends)
    dividend_income_by_ticker: dict[str, float] = defaultdict(float)
    for dividend in dividends:
        dividend_income_by_ticker[dividend.ticker] += dividend.amount

    return PortfolioMetrics(
        realized_pnl=sum(t.pnl for t in trades),
        trading212_realized_pnl=sum(f.realised_profit_loss for f in fills if f.side == "SELL"),
        win_rate=win_rate,
        average_winning_trade=average_winning_trade,
        average_losing_trade=average_losing_trade,
        expectancy=expectancy,
        profit_factor=profit_factor,
        payoff_ratio=payoff_ratio,
        average_holding_period_hours=average_holding_period_hours,
        best_trade_pnl=best_trade_pnl,
        worst_trade_pnl=worst_trade_pnl,
        current_streak=current_streak,
        longest_win_streak=longest_win_streak,
        longest_loss_streak=longest_loss_streak,
        closed_trade_count=closed_trade_count,
        performance_by_ticker=performance_by_ticker,
        entries_by_day_of_week=_count_by_day_of_week(t.entry_at for t in trades),
        exits_by_day_of_week=_count_by_day_of_week(t.exit_at for t in trades),
        entries_by_hour_of_day=_count_by_hour_of_day(t.entry_at for t in trades),
        exits_by_hour_of_day=_count_by_hour_of_day(t.exit_at for t in trades),
        max_drawdown=compute_max_drawdown(snapshots),
        dividend_income=dividend_income,
        dividend_income_by_ticker=dict(dividend_income_by_ticker),
    )


def _compute_streaks(trades: list[ClosedTrade]) -> tuple[int, int, int]:
    """Return (current_streak, longest_win_streak, longest_loss_streak), in
    trade-exit order. current_streak is positive for an active winning
    streak, negative for an active losing streak, and 0 if there are no
    trades or the most recent trade was breakeven (pnl == 0)."""
    longest_win = longest_loss = 0
    run_win = run_loss = 0
    current = 0
    for trade in trades:
        if trade.pnl > 0:
            run_win += 1
            run_loss = 0
            current = run_win
        elif trade.pnl < 0:
            run_loss += 1
            run_win = 0
            current = -run_loss
        else:
            run_win = run_loss = 0
            current = 0
        longest_win = max(longest_win, run_win)
        longest_loss = max(longest_loss, run_loss)
    return current, longest_win, longest_loss


def _count_by_day_of_week(timestamps) -> dict[str, int]:
    counts = {name: 0 for name in _DAY_NAMES}
    for ts in timestamps:
        counts[_DAY_NAMES[ts.weekday()]] += 1
    return counts


def _count_by_hour_of_day(timestamps) -> dict[str, int]:
    counts = {str(hour): 0 for hour in range(24)}
    for ts in timestamps:
        counts[str(ts.hour)] += 1
    return counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_metrics_service.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/metrics.py backend/tests/test_metrics_service.py
git commit -m "feat: add aggregate portfolio metrics computation"
```

---

## Task 6: History sync service

**Files:**
- Create: `backend/app/services/history_sync.py`
- Test: `backend/tests/test_history_sync_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_history_sync_service.py`:

```python
"""Tests for the history sync service that persists Trading212 order/dividend history."""

from unittest.mock import MagicMock

from app.models import Dividend, OrderFill
from app.services.history_sync import sync_dividends, sync_history, sync_order_fills

ORDER_PAGE_1 = {
    "items": [
        {
            "order": {"id": 1, "ticker": "AAPL_US_EQ", "side": "BUY", "currency": "USD"},
            "fill": {
                "id": 101,
                "filledAt": "2026-01-01T10:00:00Z",
                "quantity": 10.0,
                "price": 100.0,
                "type": "TRADE",
                "walletImpact": {
                    "currency": "USD",
                    "netValue": 1000.0,
                    "realisedProfitLoss": 0.0,
                    "taxes": [{"name": "COMMISSION_TURNOVER", "quantity": 1.0}],
                },
            },
        },
        {
            "order": {"id": 2, "ticker": "AAPL_US_EQ", "side": "SELL", "currency": "USD"},
            "fill": {
                "id": 102,
                "filledAt": "2026-01-05T10:00:00Z",
                "quantity": 10.0,
                "price": 110.0,
                "type": "STOCK_SPLIT",
                "walletImpact": {
                    "currency": "USD",
                    "netValue": 1100.0,
                    "realisedProfitLoss": 100.0,
                    "taxes": [],
                },
            },
        },
    ],
    "nextPagePath": "/api/v0/equity/history/orders?cursor=2&limit=50",
}
ORDER_PAGE_2 = {
    "items": [
        {
            "order": {"id": 3, "ticker": "MSFT_US_EQ", "side": "SELL", "currency": "USD"},
            "fill": {
                "id": 103,
                "filledAt": "2026-01-11T12:00:00Z",
                "quantity": 2.0,
                "price": 205.0,
                "type": "TRADE",
                "walletImpact": {
                    "currency": "USD",
                    "netValue": 410.0,
                    "realisedProfitLoss": 10.0,
                    "taxes": [],
                },
            },
        }
    ],
    "nextPagePath": None,
}
DIVIDEND_PAGE = {
    "items": [
        {
            "ticker": "AAPL_US_EQ",
            "amount": 5.0,
            "currency": "USD",
            "type": "ORDINARY",
            "paidOn": "2026-01-15T00:00:00Z",
            "reference": "div-ref-1",
        },
        {
            "ticker": "MSFT_US_EQ",
            "amount": 2.0,
            "currency": "USD",
            "type": "ORDINARY",
            "paidOn": "2026-01-20T00:00:00Z",
        },
    ],
    "nextPagePath": None,
}


def test_sync_order_fills_paginates_and_filters_non_trade_fills(db_session):
    """sync_order_fills should walk every page and only store fills with type TRADE."""
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    added = sync_order_fills(db_session, fake_client)

    assert added == 2  # fill 101 (BUY, TRADE) and fill 103 (SELL, TRADE); 102 is STOCK_SPLIT
    stored_ids = {row.id for row in db_session.query(OrderFill).all()}
    assert stored_ids == {"101", "103"}
    assert fake_client.get_historical_orders.call_count == 2
    fake_client.get_historical_orders.assert_any_call(cursor=None)
    fake_client.get_historical_orders.assert_any_call(cursor=2)


def test_sync_order_fills_sums_taxes_into_fees(db_session):
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]

    sync_order_fills(db_session, fake_client)

    stored = db_session.query(OrderFill).filter_by(id="101").one()
    assert stored.fees == 1.0
    assert stored.side == "BUY"
    assert stored.ticker == "AAPL_US_EQ"


def test_sync_order_fills_is_idempotent(db_session):
    """Running the sync twice should not create duplicate rows."""
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [
        ORDER_PAGE_1, ORDER_PAGE_2, ORDER_PAGE_1, ORDER_PAGE_2,
    ]

    sync_order_fills(db_session, fake_client)
    second_added = sync_order_fills(db_session, fake_client)

    assert second_added == 0
    assert db_session.query(OrderFill).count() == 2


def test_sync_dividends_uses_reference_or_falls_back_to_composite_key(db_session):
    """A dividend with a `reference` uses it as the id; without one, falls back
    to a composite key of ticker/date/amount."""
    fake_client = MagicMock()
    fake_client.get_dividends.side_effect = [DIVIDEND_PAGE]

    added = sync_dividends(db_session, fake_client)

    assert added == 2
    stored_ids = {row.id for row in db_session.query(Dividend).all()}
    assert "div-ref-1" in stored_ids
    assert "MSFT_US_EQ:2026-01-20T00:00:00Z:2.0" in stored_ids


def test_sync_history_syncs_both_orders_and_dividends(db_session):
    fake_client = MagicMock()
    fake_client.get_historical_orders.side_effect = [ORDER_PAGE_1, ORDER_PAGE_2]
    fake_client.get_dividends.side_effect = [DIVIDEND_PAGE]

    sync_history(db_session, fake_client)

    assert db_session.query(OrderFill).count() == 2
    assert db_session.query(Dividend).count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_history_sync_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.history_sync'`

- [ ] **Step 3: Implement the sync service**

Create `backend/app/services/history_sync.py`:

```python
"""History sync service.

Pulls Trading212's order-fill and dividend history into the local
`order_fills` / `dividends` tables. Each run walks every page of both
endpoints (page ordering isn't documented, so an early-stop-at-known-id
shortcut isn't safe) and upserts by id, skipping ids already stored. At
single-user, hundreds-of-fills scale this is a handful of API calls per run.
"""

from datetime import datetime
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from ..models import Dividend, OrderFill
from ..trading212 import Trading212Client


def _extract_cursor(next_page_path: str | None) -> int | None:
    """Pull the `cursor` query param out of a Trading212 `nextPagePath`."""
    if not next_page_path:
        return None
    query = parse_qs(urlparse(next_page_path).query)
    values = query.get("cursor")
    return int(values[0]) if values else None


def sync_order_fills(session: Session, client: Trading212Client) -> int:
    """Sync historical order fills; returns the number of new rows added.

    Only fills with type "TRADE" are stored — corporate-action fills
    (splits, stock dividends, spin-offs, etc.) are skipped since they'd
    corrupt FIFO trade reconstruction.
    """
    existing_ids = {row.id for row in session.query(OrderFill.id).all()}
    added = 0
    cursor: int | None = None
    while True:
        page = client.get_historical_orders(cursor=cursor)
        for item in page["items"]:
            fill = item["fill"]
            if fill["type"] != "TRADE":
                continue
            fill_id = str(fill["id"])
            if fill_id in existing_ids:
                continue
            order = item["order"]
            wallet_impact = fill["walletImpact"]
            fees = sum(tax["quantity"] for tax in wallet_impact.get("taxes", []))
            session.add(
                OrderFill(
                    id=fill_id,
                    order_id=str(order["id"]),
                    ticker=order["ticker"],
                    side=order["side"],
                    quantity=fill["quantity"],
                    fill_price=fill["price"],
                    net_value=wallet_impact["netValue"],
                    realised_profit_loss=wallet_impact.get("realisedProfitLoss") or 0.0,
                    fees=fees,
                    currency=wallet_impact["currency"],
                    filled_at=datetime.fromisoformat(fill["filledAt"].replace("Z", "+00:00")),
                )
            )
            existing_ids.add(fill_id)
            added += 1
        cursor = _extract_cursor(page.get("nextPagePath"))
        if cursor is None:
            break
    session.commit()
    return added


def sync_dividends(session: Session, client: Trading212Client) -> int:
    """Sync historical dividend payments; returns the number of new rows added."""
    existing_ids = {row.id for row in session.query(Dividend.id).all()}
    added = 0
    cursor: int | None = None
    while True:
        page = client.get_dividends(cursor=cursor)
        for item in page["items"]:
            dividend_id = item.get("reference") or (
                f"{item['ticker']}:{item['paidOn']}:{item['amount']}"
            )
            if dividend_id in existing_ids:
                continue
            session.add(
                Dividend(
                    id=dividend_id,
                    ticker=item["ticker"],
                    amount=item["amount"],
                    currency=item["currency"],
                    type=item["type"],
                    paid_at=datetime.fromisoformat(item["paidOn"].replace("Z", "+00:00")),
                )
            )
            existing_ids.add(dividend_id)
            added += 1
        cursor = _extract_cursor(page.get("nextPagePath"))
        if cursor is None:
            break
    session.commit()
    return added


def sync_history(session: Session, client: Trading212Client) -> None:
    """Sync both order fills and dividends; invoked on a timer by the scheduler."""
    sync_order_fills(session, client)
    sync_dividends(session, client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history_sync_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/history_sync.py backend/tests/test_history_sync_service.py
git commit -m "feat: add history sync service for order fills and dividends"
```

---

## Task 7: Wire up the scheduled history-sync job

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/scheduler.py`
- Modify: `backend/app/main.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_config.py`, add this assertion to the end of `test_settings_loads_from_environment_with_defaults`:

```python
    assert settings.history_sync_interval_minutes == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'history_sync_interval_minutes'`

- [ ] **Step 3: Add the setting**

In `backend/app/config.py`, add this line after `snapshot_interval_minutes: int = 15`:

```python
    history_sync_interval_minutes: int = 60
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Wire the job into the scheduler**

In `backend/app/scheduler.py`, change the import line:

```python
from .services.snapshot import take_snapshot
```

to:

```python
from .services.history_sync import sync_history
from .services.snapshot import take_snapshot
```

Then append to the end of the file:

```python


def run_history_sync_job() -> None:
    """Sync Trading212 order/dividend history; invoked on a timer by the scheduler."""
    client = Trading212Client(
        api_key=settings.trading212_api_key,
        api_secret=settings.trading212_api_secret,
        base_url=settings.trading212_base_url,
    )
    session = SessionLocal()
    try:
        sync_history(session, client)
    finally:
        session.close()
```

- [ ] **Step 6: Register the job in the app lifespan**

In `backend/app/main.py`, change:

```python
from .scheduler import run_snapshot_job
```

to:

```python
from .scheduler import run_history_sync_job, run_snapshot_job
```

Then change:

```python
    scheduler.add_job(run_snapshot_job, "interval", minutes=settings.snapshot_interval_minutes)
```

to:

```python
    scheduler.add_job(run_snapshot_job, "interval", minutes=settings.snapshot_interval_minutes)
    scheduler.add_job(run_history_sync_job, "interval", minutes=settings.history_sync_interval_minutes)
```

- [ ] **Step 7: Document the new env var**

Append to `backend/.env.example`:

```
HISTORY_SYNC_INTERVAL_MINUTES=60
```

- [ ] **Step 8: Run the full backend suite to confirm nothing broke**

Run: `python -m pytest -v`
Expected: PASS (all tests, including the existing scheduler/main-dependent ones)

- [ ] **Step 9: Commit**

```bash
git add backend/app/config.py backend/app/scheduler.py backend/app/main.py backend/.env.example backend/tests/test_config.py
git commit -m "feat: schedule periodic Trading212 history sync"
```

---

## Task 8: API response schemas

**Files:**
- Modify: `backend/app/schemas.py`

No dedicated test file — these are plain Pydantic models exercised via the router test in Task 9 (matching the existing pattern, where `schemas.py` has no direct unit tests of its own).

- [ ] **Step 1: Add the schemas**

Append to `backend/app/schemas.py`:

```python
class TickerPerformanceOut(BaseModel):
    ticker: str
    realizedPnl: float
    tradeCount: int
    winRate: float


class PortfolioMetricsOut(BaseModel):
    realizedPnl: float
    trading212RealizedPnl: float
    winRate: float
    averageWinningTrade: float
    averageLosingTrade: float
    expectancy: float
    profitFactor: float | None
    payoffRatio: float | None
    averageHoldingPeriodHours: float
    bestTradePnl: float | None
    worstTradePnl: float | None
    currentStreak: int
    longestWinStreak: int
    longestLossStreak: int
    closedTradeCount: int
    performanceByTicker: list[TickerPerformanceOut]
    entriesByDayOfWeek: dict[str, int]
    exitsByDayOfWeek: dict[str, int]
    entriesByHourOfDay: dict[str, int]
    exitsByHourOfDay: dict[str, int]
    maxDrawdown: float
    # Not part of the metrics service's PortfolioMetrics — computed by the
    # router from a live account-summary call, since services/metrics.py is
    # pure/no-IO and cash drag isn't a historical figure.
    cashDrag: float
    dividendIncome: float
    dividendIncomeByTicker: dict[str, float]
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `python -c "import app.schemas"`
Expected: no output, exit code 0

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: add PortfolioMetricsOut response schema"
```

---

## Task 9: API router — `GET /api/portfolio/metrics`

**Files:**
- Modify: `backend/app/routers/portfolio.py`
- Test: `backend/tests/test_portfolio_router.py`

- [ ] **Step 1: Write the failing tests**

Add to the top of `backend/tests/test_portfolio_router.py`, alongside the existing imports:

```python
from datetime import datetime, timezone

import pytest

from app.models import OrderFill
```

Add to the end of `backend/tests/test_portfolio_router.py`:

```python
def test_get_portfolio_metrics_returns_computed_metrics_and_cash_drag(client, db_session):
    """The endpoint should compute metrics from synced history and cash drag
    from a live account-summary call."""
    db_session.add_all(
        [
            OrderFill(
                id="1", order_id="1", ticker="AAPL_US_EQ", side="BUY", quantity=10.0,
                fill_price=100.0, net_value=1000.0, realised_profit_loss=0.0, fees=0.0,
                currency="USD", filled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            OrderFill(
                id="2", order_id="2", ticker="AAPL_US_EQ", side="SELL", quantity=10.0,
                fill_price=110.0, net_value=1100.0, realised_profit_loss=100.0, fees=0.0,
                currency="USD", filled_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()
    fake_client = MagicMock()
    fake_client.get_account_summary.return_value = {
        **FAKE_SUMMARY,
        "totalValue": 1000.0,
        "cash": {"availableToTrade": 250.0, "inPies": 0.0, "reservedForOrders": 0.0},
    }
    app.dependency_overrides[get_trading212_client] = lambda: fake_client

    response = client.get("/api/portfolio/metrics", headers=AUTH_HEADER)

    del app.dependency_overrides[get_trading212_client]
    assert response.status_code == 200
    body = response.json()
    assert body["closedTradeCount"] == 1
    assert body["realizedPnl"] == pytest.approx(100.0)
    assert body["winRate"] == pytest.approx(1.0)
    assert body["cashDrag"] == pytest.approx(0.25)


def test_get_portfolio_metrics_requires_auth(client):
    response = client.get("/api/portfolio/metrics")

    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_portfolio_router.py -v`
Expected: FAIL with `404 != 200` (route doesn't exist yet)

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/portfolio.py`, change the imports:

```python
from ..models import PortfolioSnapshot
from ..schemas import AccountSummary, CashBreakdown, PortfolioCurrent, PortfolioSnapshotOut, Position
```

to:

```python
from ..models import Dividend, OrderFill, PortfolioSnapshot
from ..schemas import (
    AccountSummary,
    CashBreakdown,
    PortfolioCurrent,
    PortfolioMetricsOut,
    PortfolioSnapshotOut,
    Position,
    TickerPerformanceOut,
)
from ..services.metrics import compute_portfolio_metrics
```

Then append to the end of the file:

```python


@router.get("/portfolio/metrics", response_model=PortfolioMetricsOut)
def get_portfolio_metrics(
    db: Session = Depends(get_db),
    client: Trading212Client = Depends(get_trading212_client),
) -> PortfolioMetricsOut:
    """Compute trade performance metrics from synced Trading212 history, plus
    a live cash-drag figure from the current account summary."""
    fills = db.query(OrderFill).order_by(OrderFill.filled_at).all()
    dividends = db.query(Dividend).all()
    snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.taken_at).all()
    metrics = compute_portfolio_metrics(fills, dividends, snapshots)

    try:
        summary = client.get_account_summary()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Trading212 - check your API credentials.",
        ) from exc
    total_value = summary["totalValue"]
    cash_drag = summary["cash"]["availableToTrade"] / total_value if total_value else 0.0

    return PortfolioMetricsOut(
        realizedPnl=metrics.realized_pnl,
        trading212RealizedPnl=metrics.trading212_realized_pnl,
        winRate=metrics.win_rate,
        averageWinningTrade=metrics.average_winning_trade,
        averageLosingTrade=metrics.average_losing_trade,
        expectancy=metrics.expectancy,
        profitFactor=metrics.profit_factor,
        payoffRatio=metrics.payoff_ratio,
        averageHoldingPeriodHours=metrics.average_holding_period_hours,
        bestTradePnl=metrics.best_trade_pnl,
        worstTradePnl=metrics.worst_trade_pnl,
        currentStreak=metrics.current_streak,
        longestWinStreak=metrics.longest_win_streak,
        longestLossStreak=metrics.longest_loss_streak,
        closedTradeCount=metrics.closed_trade_count,
        performanceByTicker=[
            TickerPerformanceOut(
                ticker=tp.ticker,
                realizedPnl=tp.realized_pnl,
                tradeCount=tp.trade_count,
                winRate=tp.win_rate,
            )
            for tp in metrics.performance_by_ticker
        ],
        entriesByDayOfWeek=metrics.entries_by_day_of_week,
        exitsByDayOfWeek=metrics.exits_by_day_of_week,
        entriesByHourOfDay=metrics.entries_by_hour_of_day,
        exitsByHourOfDay=metrics.exits_by_hour_of_day,
        maxDrawdown=metrics.max_drawdown,
        cashDrag=cash_drag,
        dividendIncome=metrics.dividend_income,
        dividendIncomeByTicker=metrics.dividend_income_by_ticker,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_portfolio_router.py -v`
Expected: PASS (6 tests: the 2 new plus the existing 4)

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest -v`
Expected: PASS (all tests)

- [ ] **Step 6: Lint and format**

Run: `ruff check .` then `ruff format --check .`
Expected: both report no issues (run `ruff format .` and re-stage if formatting differs)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/portfolio.py backend/tests/test_portfolio_router.py
git commit -m "feat: add GET /api/portfolio/metrics endpoint"
```

---

## Task 10: Frontend types

**Files:**
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Add the types**

Append to `frontend/lib/types.ts`:

```typescript
export interface TickerPerformance {
  ticker: string;
  realizedPnl: number;
  tradeCount: number;
  winRate: number;
}

export interface PortfolioMetrics {
  realizedPnl: number;
  trading212RealizedPnl: number;
  winRate: number;
  averageWinningTrade: number;
  averageLosingTrade: number;
  expectancy: number;
  profitFactor: number | null;
  payoffRatio: number | null;
  averageHoldingPeriodHours: number;
  bestTradePnl: number | null;
  worstTradePnl: number | null;
  currentStreak: number;
  longestWinStreak: number;
  longestLossStreak: number;
  closedTradeCount: number;
  performanceByTicker: TickerPerformance[];
  entriesByDayOfWeek: Record<string, number>;
  exitsByDayOfWeek: Record<string, number>;
  entriesByHourOfDay: Record<string, number>;
  exitsByHourOfDay: Record<string, number>;
  maxDrawdown: number;
  cashDrag: number;
  dividendIncome: number;
  dividendIncomeByTicker: Record<string, number>;
}
```

- [ ] **Step 2: Verify the project still typechecks**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat: add PortfolioMetrics frontend types"
```

---

## Task 11: Frontend API client

**Files:**
- Modify: `frontend/lib/api.ts`
- Test: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `frontend/lib/__tests__/api.test.ts`, inside the `describe("portfolio API client", ...)` block, after the existing `"fetches portfolio history from the backend"` test:

```typescript
  it("fetches portfolio metrics from the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await getPortfolioMetrics();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://backend.example.com/api/portfolio/metrics",
      expect.objectContaining({ headers: { Authorization: "Bearer test-key" } })
    );
  });

  it("throws when the metrics endpoint responds with an error status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    );

    await expect(getPortfolioMetrics()).rejects.toThrow("Failed to fetch portfolio metrics: 500");
  });
```

Update the import line at the top of the file to:

```typescript
import { getPortfolioCurrent, getPortfolioHistory, getPortfolioMetrics } from "../api";
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npm run test`
Expected: FAIL — `getPortfolioMetrics is not a function` (or a TypeScript error on the import)

- [ ] **Step 3: Implement the client function**

In `frontend/lib/api.ts`, change the import line:

```typescript
import type { PortfolioCurrent, PortfolioSnapshot } from "./types";
```

to:

```typescript
import type { PortfolioCurrent, PortfolioMetrics, PortfolioSnapshot } from "./types";
```

Then append to the end of the file:

```typescript

export async function getPortfolioMetrics(): Promise<PortfolioMetrics> {
  const response = await fetch(backendUrl("/api/portfolio/metrics"), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio metrics: ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/__tests__/api.test.ts
git commit -m "feat: add getPortfolioMetrics frontend API client"
```

---

## Task 12: Frontend components — `PerformanceMetrics` and `TickerPerformanceTable`

**Files:**
- Create: `frontend/components/PerformanceMetrics.tsx`
- Create: `frontend/components/TickerPerformanceTable.tsx`
- Test: `frontend/components/__tests__/PerformanceMetrics.test.tsx`
- Test: `frontend/components/__tests__/TickerPerformanceTable.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/components/__tests__/PerformanceMetrics.test.tsx`:

```typescript
// Tests for PerformanceMetrics: verifies it renders realized P/L, win rate,
// expectancy, drawdown, and cash drag, and shows a placeholder for ratios
// that are undefined when there are no closed trades.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import type { PortfolioMetrics } from "../../lib/types";
import { PerformanceMetrics } from "../PerformanceMetrics";

const METRICS: PortfolioMetrics = {
  realizedPnl: 57,
  trading212RealizedPnl: 57,
  winRate: 0.6666666666666666,
  averageWinningTrade: 54,
  averageLosingTrade: -51,
  expectancy: 19,
  profitFactor: 2.12,
  payoffRatio: 1.06,
  averageHoldingPeriodHours: 56,
  bestTradePnl: 98,
  worstTradePnl: -51,
  currentStreak: -1,
  longestWinStreak: 2,
  longestLossStreak: 1,
  closedTradeCount: 3,
  performanceByTicker: [],
  entriesByDayOfWeek: {},
  exitsByDayOfWeek: {},
  entriesByHourOfDay: {},
  exitsByHourOfDay: {},
  maxDrawdown: 0.25,
  cashDrag: 0.1,
  dividendIncome: 10,
  dividendIncomeByTicker: {},
};

describe("PerformanceMetrics", () => {
  it("renders realized P/L, win rate, expectancy, drawdown, and cash drag", () => {
    render(<PerformanceMetrics metrics={METRICS} currency="USD" />);

    expect(screen.getByText(formatCurrency(57, "USD"))).toBeInTheDocument();
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(19, "USD"))).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
    expect(screen.getByText("10.0%")).toBeInTheDocument();
  });

  it("shows a placeholder dash for profit factor and payoff ratio when there are no closed trades", () => {
    render(
      <PerformanceMetrics
        metrics={{ ...METRICS, closedTradeCount: 0, winRate: 0, profitFactor: null, payoffRatio: null }}
        currency="USD"
      />
    );

    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });
});
```

Create `frontend/components/__tests__/TickerPerformanceTable.test.tsx`:

```typescript
// Tests for TickerPerformanceTable: verifies row rendering and the empty-state message.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatCurrency } from "../../lib/format";
import { TickerPerformanceTable } from "../TickerPerformanceTable";

describe("TickerPerformanceTable", () => {
  it("renders a row per ticker", () => {
    render(
      <TickerPerformanceTable
        currency="USD"
        performanceByTicker={[{ ticker: "AAPL_US_EQ", realizedPnl: 47, tradeCount: 2, winRate: 0.5 }]}
      />
    );

    expect(screen.getByText("AAPL_US_EQ")).toBeInTheDocument();
    expect(screen.getByText(formatCurrency(47, "USD"))).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("renders an empty state when there are no closed trades", () => {
    render(<TickerPerformanceTable currency="USD" performanceByTicker={[]} />);

    expect(screen.getByText("No closed trades yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm run test`
Expected: FAIL — cannot find module `../PerformanceMetrics` / `../TickerPerformanceTable`

- [ ] **Step 3: Implement the components**

Create `frontend/components/PerformanceMetrics.tsx`:

```typescript
// Renders a stats grid of trade performance and account-level metrics: realized
// P/L, win rate, expectancy, profit factor, payoff ratio, holding period, max
// drawdown, cash drag, and dividend income. Trade-derived figures default to
// 0 (or a dash for ratios undefined with no losing trades) when there are no
// closed trades yet, so the grid always renders rather than needing an
// empty-state gate.

import { formatCurrency } from "../lib/format";
import type { PortfolioMetrics } from "../lib/types";

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatRatio(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

export function PerformanceMetrics({ metrics, currency }: { metrics: PortfolioMetrics; currency: string }) {
  const isProfit = metrics.realizedPnl >= 0;
  return (
    <div className="grid grid-cols-2 gap-4 rounded-lg border border-neutral-200 p-6 sm:grid-cols-4">
      <div>
        <p className="text-sm text-neutral-500">Realized P/L</p>
        <p className={`text-2xl font-semibold ${isProfit ? "text-green-600" : "text-red-600"}`}>
          {formatCurrency(metrics.realizedPnl, currency)}
        </p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Win rate</p>
        <p className="text-2xl font-semibold">{formatPercent(metrics.winRate)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Expectancy</p>
        <p className="text-2xl font-semibold">{formatCurrency(metrics.expectancy, currency)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Profit factor</p>
        <p className="text-2xl font-semibold">{formatRatio(metrics.profitFactor)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Payoff ratio</p>
        <p className="text-2xl font-semibold">{formatRatio(metrics.payoffRatio)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Avg. holding period</p>
        <p className="text-2xl font-semibold">{(metrics.averageHoldingPeriodHours / 24).toFixed(1)}d</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Max drawdown</p>
        <p className="text-2xl font-semibold">{formatPercent(metrics.maxDrawdown)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Cash drag</p>
        <p className="text-2xl font-semibold">{formatPercent(metrics.cashDrag)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Dividend income</p>
        <p className="text-2xl font-semibold">{formatCurrency(metrics.dividendIncome, currency)}</p>
      </div>
    </div>
  );
}
```

Create `frontend/components/TickerPerformanceTable.tsx`:

```typescript
// Renders a table of realized trading performance broken down by ticker.
// Displays an empty state message when there are no closed trades.

import { formatCurrency } from "../lib/format";
import type { TickerPerformance } from "../lib/types";

export function TickerPerformanceTable({
  performanceByTicker,
  currency,
}: {
  performanceByTicker: TickerPerformance[];
  currency: string;
}) {
  if (performanceByTicker.length === 0) {
    return <p className="text-neutral-500">No closed trades yet.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500">
          <th className="py-2">Ticker</th>
          <th className="py-2">Realized P/L</th>
          <th className="py-2">Trades</th>
          <th className="py-2">Win rate</th>
        </tr>
      </thead>
      <tbody>
        {performanceByTicker.map((row) => (
          <tr key={row.ticker} className="border-b border-neutral-100">
            <td className="py-2 font-medium">{row.ticker}</td>
            <td className={`py-2 ${row.realizedPnl >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(row.realizedPnl, currency)}
            </td>
            <td className="py-2">{row.tradeCount}</td>
            <td className="py-2">{(row.winRate * 100).toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test`
Expected: PASS (all tests)

- [ ] **Step 5: Lint**

Run: `npm run lint`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/components/PerformanceMetrics.tsx frontend/components/TickerPerformanceTable.tsx frontend/components/__tests__/PerformanceMetrics.test.tsx frontend/components/__tests__/TickerPerformanceTable.test.tsx
git commit -m "feat: add PerformanceMetrics and TickerPerformanceTable components"
```

---

## Task 13: Wire the Performance section into the dashboard page

**Files:**
- Modify: `frontend/app/page.tsx`

No dedicated test — `page.tsx` is an async Server Component and has no existing test file (matching current convention); it's covered by the manual verification in Task 14.

- [ ] **Step 1: Update the page**

Replace the full contents of `frontend/app/page.tsx` with:

```typescript
// Main dashboard Server Component: fetches live portfolio data from the backend API
// server-side (so BACKEND_URL/DASHBOARD_API_KEY never reach the browser) and renders
// the summary, equity curve, positions table, and performance metrics.
export const dynamic = "force-dynamic";

import { EquityCurveChart } from "../components/EquityCurveChart";
import { PerformanceMetrics } from "../components/PerformanceMetrics";
import { PortfolioSummary } from "../components/PortfolioSummary";
import { PositionsTable } from "../components/PositionsTable";
import { TickerPerformanceTable } from "../components/TickerPerformanceTable";
import { getPortfolioCurrent, getPortfolioHistory, getPortfolioMetrics } from "../lib/api";

export default async function DashboardPage() {
  const [current, history, metrics] = await Promise.all([
    getPortfolioCurrent(),
    getPortfolioHistory(),
    getPortfolioMetrics(),
  ]);

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
      <section>
        <h2 className="mb-4 text-xl font-semibold">Performance</h2>
        <PerformanceMetrics metrics={metrics} currency={current.account.currency} />
        <div className="mt-6">
          <TickerPerformanceTable
            performanceByTicker={metrics.performanceByTicker}
            currency={current.account.currency}
          />
        </div>
      </section>
    </main>
  );
}
```

- [ ] **Step 2: Run the frontend build to confirm it compiles**

Run (from `frontend/`): `npm run build`
Expected: build succeeds (the page is force-dynamic, so it isn't prerendered against a live backend at build time)

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: add Performance section to the dashboard page"
```

---

## Task 14: Full verification pass

Not a TDD task — a final check that every piece works together, matching this project's practice of running the app in a browser before calling UI work done.

- [ ] **Step 1: Full backend suite**

Run (from `backend/`, venv activated): `python -m pytest -v`
Expected: PASS, all tests (existing + new)

- [ ] **Step 2: Backend lint and format**

Run: `ruff check .` then `ruff format --check .`
Expected: both clean

- [ ] **Step 3: Full frontend suite**

Run (from `frontend/`): `npm run test`
Expected: PASS, all tests (existing + new)

- [ ] **Step 4: Frontend lint and build**

Run: `npm run lint` then `npm run build`
Expected: both clean/succeed

- [ ] **Step 5: Manual browser check**

Start both dev servers (`uvicorn app.main:app --reload` from `backend/`, `npm run dev` from `frontend/`), open the dashboard in a browser, and confirm the new "Performance" section renders below "Open positions" — the stats grid (realized P/L, win rate, expectancy, profit factor, payoff ratio, holding period, max drawdown, cash drag, dividend income) and the by-ticker table. Since there's no synced history yet on a fresh DB, expect to see zeros/dashes and an empty by-ticker table — that's the correct zero-trade rendering verified in Task 12, not a bug. To see real numbers, either wait for the scheduled sync job to run once (`HISTORY_SYNC_INTERVAL_MINUTES`, default 60) or manually invoke `sync_history` once against the real Trading212 credentials already in `backend/.env`.

- [ ] **Step 6: Report status**

If everything above is clean, the feature is complete on `feature/intialDesign` and ready for the user to review (per this project's usual finishing-a-branch flow — no PR unless asked).
