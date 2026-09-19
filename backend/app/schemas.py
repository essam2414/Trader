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
