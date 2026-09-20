// Currency formatting helper for displaying monetary values in the UI.
// Uses Intl.NumberFormat to ensure consistent locale-aware formatting across the application.

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
