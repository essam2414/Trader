// Renders a table of realized trading performance broken down by ticker.
// Displays an empty state message when there are no closed trades.

import { formatCurrency } from "../lib/format";
import type { TickerPerformance } from "../lib/types";

export function TickerPerformanceTable({
  performanceByTicker,
  currency,
}: {
  performanceByTicker: TickerPerformance[];
  currency: string;
}) {
  if (performanceByTicker.length === 0) {
    return <p className="text-neutral-500">No closed trades yet.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500">
          <th className="py-2">Ticker</th>
          <th className="py-2">Realized P/L</th>
          <th className="py-2">Trades</th>
          <th className="py-2">Win rate</th>
        </tr>
      </thead>
      <tbody>
        {performanceByTicker.map((row) => (
          <tr key={row.ticker} className="border-b border-neutral-100">
            <td className="py-2 font-medium">{row.ticker}</td>
            <td className={`py-2 ${row.realizedPnl >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(row.realizedPnl, currency)}
            </td>
            <td className="py-2">{row.tradeCount}</td>
            <td className="py-2">{(row.winRate * 100).toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
