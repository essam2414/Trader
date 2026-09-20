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

export interface TickerPerformance {
  ticker: string;
  realizedPnl: number;
  tradeCount: number;
  winRate: number;
}

export interface Trade {
  ticker: string;
  quantity: number;
  entryPrice: number;
  entryAt: string;
  exitPrice: number;
  exitAt: string;
  pnl: number;
  holdingPeriodHours: number;
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
  dividendIncome: number;
  dividendIncomeByTicker: Record<string, number>;
  trades: Trade[];
}

export interface WatchlistSearchResult {
  assetId: string;
  symbol: string;
  name: string;
  exchange: string;
}

export interface SparklinePoint {
  timestamp: string;
  close: number;
}

export type QuoteFreshness = "fresh" | "stale" | "unavailable";

export interface WatchlistQuote {
  price: number | null;
  previousClose: number | null;
  dollarChange: number | null;
  percentChange: number | null;
  sparkline: SparklinePoint[];
  feed: string;
  sourceTimestamp: string | null;
  sourceType: string | null;
  freshness: QuoteFreshness;
  isExtendedHours: boolean;
}

export interface WatchlistEntry {
  assetId: string;
  symbol: string;
  name: string;
  exchange: string;
  sortOrder: number;
  addedAt: string;
  logoUrl: string;
  quote: WatchlistQuote;
}
