"""Tests for the trade metrics service (FIFO matching and aggregate calculations)."""

from datetime import datetime, timezone

import pytest

from app.models import Dividend, OrderFill, PortfolioSnapshot
from app.services.metrics import compute_max_drawdown, compute_portfolio_metrics, match_trades


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
            taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            total_value=1000.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            total_value=1200.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            total_value=900.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            total_value=1100.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
    ]

    assert compute_max_drawdown(snapshots) == pytest.approx(0.25)


def test_compute_max_drawdown_is_zero_with_fewer_than_two_snapshots():
    assert compute_max_drawdown([]) == 0.0
    assert (
        compute_max_drawdown(
            [
                PortfolioSnapshot(
                    taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    total_value=1000.0,
                    unrealized_profit_loss=0.0,
                    currency="USD",
                )
            ]
        )
        == 0.0
    )


def test_compute_portfolio_metrics_aggregates_trades_dividends_and_drawdown():
    fills = [
        # AAPL: win. realised_profit_loss is set equal to the FIFO result here
        # deliberately, so this fixture doubles as a check that the two P&L
        # figures line up when there's no scaling in/out to cause divergence.
        _fill(
            "1",
            "AAPL_US_EQ",
            "BUY",
            10.0,
            100.0,
            datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
            fees=1.0,
        ),
        _fill(
            "2",
            "AAPL_US_EQ",
            "SELL",
            10.0,
            110.0,
            datetime(2026, 1, 5, 10, tzinfo=timezone.utc),
            fees=1.0,
            realised_profit_loss=98.0,
        ),
        # MSFT: win
        _fill(
            "3",
            "MSFT_US_EQ",
            "BUY",
            2.0,
            200.0,
            datetime(2026, 1, 10, 12, tzinfo=timezone.utc),
        ),
        _fill(
            "4",
            "MSFT_US_EQ",
            "SELL",
            2.0,
            205.0,
            datetime(2026, 1, 11, 12, tzinfo=timezone.utc),
            realised_profit_loss=10.0,
        ),
        # AAPL: loss
        _fill(
            "5",
            "AAPL_US_EQ",
            "BUY",
            5.0,
            50.0,
            datetime(2026, 2, 1, 9, tzinfo=timezone.utc),
            fees=0.5,
        ),
        _fill(
            "6",
            "AAPL_US_EQ",
            "SELL",
            5.0,
            40.0,
            datetime(2026, 2, 3, 9, tzinfo=timezone.utc),
            fees=0.5,
            realised_profit_loss=-51.0,
        ),
    ]
    dividends = [
        Dividend(
            id="d1",
            ticker="AAPL_US_EQ",
            amount=5.0,
            currency="USD",
            type="ORDINARY",
            paid_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        ),
        Dividend(
            id="d2",
            ticker="AAPL_US_EQ",
            amount=3.0,
            currency="USD",
            type="ORDINARY",
            paid_at=datetime(2026, 1, 25, tzinfo=timezone.utc),
        ),
        Dividend(
            id="d3",
            ticker="MSFT_US_EQ",
            amount=2.0,
            currency="USD",
            type="ORDINARY",
            paid_at=datetime(2026, 1, 25, tzinfo=timezone.utc),
        ),
    ]
    snapshots = [
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            total_value=1000.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            total_value=1200.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            total_value=900.0,
            unrealized_profit_loss=0.0,
            currency="USD",
        ),
        PortfolioSnapshot(
            taken_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            total_value=1100.0,
            unrealized_profit_loss=0.0,
            currency="USD",
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
