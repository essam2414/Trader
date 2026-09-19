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

    Trading212 signs fill quantity by direction (negative for SELL, positive
    for BUY) rather than sending a plain magnitude; `side` already carries
    the direction, so quantity is normalized to its absolute value here.
    """
    fills_by_ticker: dict[str, list[OrderFill]] = defaultdict(list)
    for fill in fills:
        fills_by_ticker[fill.ticker].append(fill)

    trades: list[ClosedTrade] = []
    for ticker, ticker_fills in fills_by_ticker.items():
        open_lots: deque = deque()
        for fill in sorted(ticker_fills, key=lambda f: f.filled_at):
            quantity = abs(fill.quantity)
            if fill.side == "BUY":
                fee_per_unit = fill.fees / quantity if quantity else 0.0
                open_lots.append(
                    {
                        "quantity": quantity,
                        "price": fill.fill_price,
                        "filled_at": fill.filled_at,
                        "fee_per_unit": fee_per_unit,
                    }
                )
            elif fill.side == "SELL":
                remaining = quantity
                sell_fee_per_unit = fill.fees / quantity if quantity else 0.0
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
    closed_trades: list[ClosedTrade]


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
    payoff_ratio = average_winning_trade / abs(average_losing_trade) if average_losing_trade != 0 else None
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
        closed_trades=sorted(trades, key=lambda t: t.exit_at, reverse=True),
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
