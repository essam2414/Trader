// Currency formatting helper for displaying monetary values in the UI.
// Uses Intl.NumberFormat to ensure consistent locale-aware formatting across the application.

/**
 * Converts a Trading 212 instrument code into the ticker shown to users.
 * For example, AAOI_US_EQ becomes AAOI.
 */
export function formatTicker(ticker: string): string {
  return ticker.replace(/_[^_]+_EQ$/, "");
}

export function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(value);
}

/** Compact USD presentation for live watchlist quotes. */
export function formatWatchlistPrice(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    currencyDisplay: "narrowSymbol",
  }).format(value);
}
