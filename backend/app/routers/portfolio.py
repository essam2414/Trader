"""Portfolio API routes.

Exposes the current live portfolio (account summary + positions, fetched
live from Trading212) and the historical equity-curve data (stored
PortfolioSnapshot rows). All routes require the shared dashboard API key.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..dependencies import get_db, get_portfolio_current_cache, get_trading212_client
from ..models import Dividend, OrderFill, PortfolioSnapshot
from ..schemas import (
    AccountSummary,
    CashBreakdown,
    PortfolioCurrent,
    PortfolioMetricsOut,
    PortfolioSnapshotOut,
    Position,
    TickerPerformanceOut,
    TradeOut,
)
from ..services.metrics import compute_portfolio_metrics
from ..services.portfolio_current import PortfolioCurrentCache
from ..trading212 import Trading212Client

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/portfolio/current", response_model=PortfolioCurrent)
def get_current_portfolio(
    client: Trading212Client = Depends(get_trading212_client),
    cache: PortfolioCurrentCache = Depends(get_portfolio_current_cache),
) -> PortfolioCurrent:
    """Fetch the live account summary and open positions from Trading212.

    Translates any Trading212 connection/auth failure into a 502 so the frontend
    can show a clear "Trading212 isn't connected" message instead of an opaque 500.
    """

    def load() -> PortfolioCurrent:
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
                    currency=p["instrument"]["currency"],
                    quantity=p["quantity"],
                    averagePricePaid=p["averagePricePaid"],
                    currentPrice=p["currentPrice"],
                    currentValue=p["walletImpact"]["currentValue"],
                    unrealizedProfitLoss=p["walletImpact"]["unrealizedProfitLoss"],
                )
                for p in positions
            ],
        )

    try:
        return cache.get(load)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Trading212 - check your API credentials.",
        ) from exc


@router.get("/portfolio/history", response_model=list[PortfolioSnapshotOut])
def get_portfolio_history(db: Session = Depends(get_db)) -> list[PortfolioSnapshotOut]:
    """Return all stored portfolio snapshots, oldest first, for the equity-curve chart."""
    rows = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.taken_at).all()
    return [
        PortfolioSnapshotOut(
            takenAt=row.taken_at,
            totalValue=row.total_value,
            unrealizedProfitLoss=row.unrealized_profit_loss,
        )
        for row in rows
    ]


@router.get("/portfolio/metrics", response_model=PortfolioMetricsOut)
def get_portfolio_metrics(db: Session = Depends(get_db)) -> PortfolioMetricsOut:
    """Compute trade performance metrics purely from synced Trading212 history
    stored in the DB. Deliberately makes no live Trading212 call: cash drag
    needs only totalValue/cash.availableToTrade, both of which the frontend
    already has from /portfolio/current, which it fetches in the same
    dashboard load - an independent call here would just race that one for
    Trading212's request budget for no benefit."""
    fills = db.query(OrderFill).order_by(OrderFill.filled_at).all()
    dividends = db.query(Dividend).all()
    snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.taken_at).all()
    metrics = compute_portfolio_metrics(fills, dividends, snapshots)

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
        dividendIncome=metrics.dividend_income,
        dividendIncomeByTicker=metrics.dividend_income_by_ticker,
        trades=[
            TradeOut(
                ticker=t.ticker,
                quantity=t.quantity,
                entryPrice=t.entry_price,
                entryAt=t.entry_at,
                exitPrice=t.exit_price,
                exitAt=t.exit_at,
                pnl=t.pnl,
                holdingPeriodHours=t.holding_period.total_seconds() / 3600,
            )
            for t in metrics.closed_trades
        ],
    )
