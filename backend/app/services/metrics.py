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
