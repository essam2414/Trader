// Shared TypeScript types that mirror the backend's Pydantic schemas.
// Field names must remain in sync with backend/app/schemas.py — these are the wire contract.

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
  currency: string;
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
