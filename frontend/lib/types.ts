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
  weeklyRealizedProfitLoss: number;
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
  entryPriceCurrency: string;
  entryAt: string;
  exitPrice: number;
  exitPriceCurrency: string;
  exitAt: string;
  pnl: number;
  holdingPeriodHours: number;
}

export interface RealizedPnlEvent {
  takenAt: string;
  realizedPnl: number;
}

export interface PortfolioMetrics {
  realizedPnl: number;
  trading212RealizedPnl: number;
  totalWinningTradePnl: number;
  totalLosingTradePnl: number;
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
  realizedPnlTimeline: RealizedPnlEvent[];
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
  isDelayed: boolean;
  delaySeconds: number | null;
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

export interface WatchlistPositionPrice {
  purchasePrice: number | null;
  purchasePriceCurrency: string | null;
}

export type ChartRange = "1D" | "1W" | "1M" | "3M" | "1Y" | "MAX";

export interface StockChartBar {
  startsAt: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  session: "pre_market" | "regular" | "after_hours" | "overnight";
}

export interface StockChart {
  assetId: string;
  symbol: string;
  name: string;
  range: ChartRange;
  intervalSeconds: number;
  canonicalFeed: "sip";
  adjustment: "raw";
  canonicalThrough: string;
  delaySeconds: number;
  canonicalBars: StockChartBar[];
  provisionalIexBars: StockChartBar[];
}

export type MarketSessionPhase = "pre_market" | "regular" | "after_hours" | "overnight" | "closed";

export interface MarketSession {
  phase: MarketSessionPhase;
  asOf: string;
  endsAt: string | null;
  nextPhase: Exclude<MarketSessionPhase, "closed"> | null;
  nextPhaseStartsAt: string | null;
  isEarlyClose: boolean;
}

export interface CatalystCard {
  id: number;
  headline: string;
  shortSummary: string;
  watchlistSymbols: string[];
  category: string;
  direction: "upside" | "downside" | "unclear";
  status: "ready" | "pending";
  releasedAt: string | null;
  firstSeenAt: string;
  updatedAt: string;
}

export interface CatalystDetail extends CatalystCard {
  detailSummary: string;
  relevanceReason: string;
  keyFacts: string[];
  unknowns: string[];
  sources: {
    title: string;
    provider: string;
    url: string;
    publishedAt: string | null;
  }[];
}

export interface NewsStatus {
  lastSuccessfulRunAt: string | null;
  failedSources: string[];
  sourceErrors: SourceError[];
  pendingSummaries: number;
}

export interface SourceError {
  source: string;
  message: string;
}

export interface MarketEvent {
  id: string;
  title: string;
  category: string;
  scope: "watchlist" | "us_market";
  eventDate: string;
  previousEventDate: string | null;
  startsAt: string | null;
  timePrecision: "exact" | "date_only" | "window";
  dateStatus: "confirmed" | "estimated" | "changed" | "cancelled";
  watchlistSymbols: string[];
  sourceUrl: string;
  lastVerifiedAt: string;
}

export interface EventRefreshResult {
  refreshedSources: number;
  refreshedEvents: number;
  failedSources: string[];
}

export interface EventStatus {
  lastSuccessfulRunAt: string | null;
  failedSources: string[];
  sourceErrors: SourceError[];
}

export interface NewsRefreshResult {
  refreshedSources: number;
  refreshedStories: number;
  failedSources: string[];
}
