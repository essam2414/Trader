"""Pydantic response schemas for the portfolio API.

These models mirror (a trimmed, camelCase-friendly subset of) the Trading212
API response shapes and the stored PortfolioSnapshot rows, forming the
frontend-facing JSON contract for the portfolio router.
"""

from datetime import datetime
from typing import Literal

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
    weeklyRealizedProfitLoss: float


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


class RealizedPnlEventOut(BaseModel):
    takenAt: datetime
    realizedPnl: float


class TickerPerformanceOut(BaseModel):
    ticker: str
    realizedPnl: float
    tradeCount: int
    winRate: float


class TradeOut(BaseModel):
    ticker: str
    quantity: float
    entryPrice: float
    entryPriceCurrency: str
    entryAt: datetime
    exitPrice: float
    exitPriceCurrency: str
    exitAt: datetime
    pnl: float
    holdingPeriodHours: float


class PortfolioMetricsOut(BaseModel):
    realizedPnl: float
    trading212RealizedPnl: float
    totalWinningTradePnl: float
    totalLosingTradePnl: float
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
    trades: list[TradeOut]
    realizedPnlTimeline: list[RealizedPnlEventOut]


class WatchlistSearchResult(BaseModel):
    assetId: str
    symbol: str
    name: str
    exchange: str


class WatchlistAdd(BaseModel):
    assetId: str


class WatchlistOrderUpdate(BaseModel):
    assetIds: list[str]


class SparklinePoint(BaseModel):
    timestamp: datetime
    close: float


class WatchlistQuoteOut(BaseModel):
    price: float | None
    previousClose: float | None
    dollarChange: float | None
    percentChange: float | None
    sparkline: list[SparklinePoint]
    feed: str
    sourceTimestamp: datetime | None
    sourceType: str | None
    freshness: str
    isExtendedHours: bool
    isDelayed: bool
    delaySeconds: int | None


class WatchlistEntryOut(BaseModel):
    assetId: str
    symbol: str
    name: str
    exchange: str
    sortOrder: int
    addedAt: datetime
    logoUrl: str
    quote: WatchlistQuoteOut


class StockChartBarOut(BaseModel):
    startsAt: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    session: Literal["pre_market", "regular", "after_hours", "overnight"]


class WatchlistPositionPriceOut(BaseModel):
    purchasePrice: float | None
    purchasePriceCurrency: str | None


class StockChartOut(BaseModel):
    assetId: str
    symbol: str
    name: str
    range: Literal["1D", "1W", "1M", "3M", "1Y", "MAX"]
    intervalSeconds: int
    canonicalFeed: Literal["sip"]
    adjustment: Literal["raw"]
    canonicalThrough: datetime
    delaySeconds: int
    canonicalBars: list[StockChartBarOut]
    provisionalIexBars: list[StockChartBarOut]


class MarketSessionOut(BaseModel):
    phase: Literal["pre_market", "regular", "after_hours", "overnight", "closed"]
    asOf: datetime
    endsAt: datetime | None
    nextPhase: Literal["pre_market", "regular", "after_hours", "overnight"] | None
    nextPhaseStartsAt: datetime | None
    isEarlyClose: bool


class CatalystCardOut(BaseModel):
    id: int
    headline: str
    shortSummary: str
    watchlistSymbols: list[str]
    category: str
    direction: str
    status: str
    releasedAt: datetime | None
    firstSeenAt: datetime
    updatedAt: datetime


class CatalystSourceOut(BaseModel):
    title: str
    provider: str
    url: str
    publishedAt: datetime | None


class CatalystDetailOut(CatalystCardOut):
    detailSummary: str
    relevanceReason: str
    keyFacts: list[str]
    unknowns: list[str]
    sources: list[CatalystSourceOut]


class NewsStatusOut(BaseModel):
    lastSuccessfulRunAt: datetime | None
    failedSources: list[str]
    pendingSummaries: int


class MarketEventOut(BaseModel):
    id: str
    title: str
    category: str
    scope: str
    eventDate: str
    previousEventDate: str | None
    startsAt: datetime | None
    timePrecision: str
    dateStatus: str
    watchlistSymbols: list[str]
    sourceUrl: str
    lastVerifiedAt: datetime


class EventRefreshOut(BaseModel):
    refreshedSources: int
    refreshedEvents: int
    failedSources: list[str]
