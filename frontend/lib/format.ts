// Currency formatting helper for displaying monetary values in the UI.
// Uses Intl.NumberFormat to ensure consistent locale-aware formatting across the application.

export function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(value);
}
