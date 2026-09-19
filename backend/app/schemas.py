"""Pydantic response schemas for the portfolio API.

These models mirror (a trimmed, camelCase-friendly subset of) the Trading212
API response shapes and the stored PortfolioSnapshot rows, forming the
frontend-facing JSON contract for the portfolio router.
"""

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
    # `currency` is the instrument's own trading currency (may differ from the
    # account's base currency); price fields below are quoted in it.
    ticker: str
    name: str
    currency: str
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
    dividendIncome: float
    dividendIncomeByTicker: dict[str, float]
