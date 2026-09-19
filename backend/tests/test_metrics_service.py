"""Tests for the trade metrics service (FIFO matching and aggregate calculations)."""

from datetime import datetime, timezone

import pytest

from app.models import OrderFill, PortfolioSnapshot
from app.services.metrics import compute_max_drawdown, match_trades


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
