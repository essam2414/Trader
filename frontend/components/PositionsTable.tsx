// Renders a table of open positions with quantity, prices, value, and P/L.
// Displays an empty state message when no positions are held.

import { formatCurrency } from "../lib/format";
import type { Position } from "../lib/types";

export function PositionsTable({ positions, currency }: { positions: Position[]; currency: string }) {
  if (positions.length === 0) {
    return <p className="text-sm text-zinc-500">No open positions.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-zinc-800">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-950/40">
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Ticker</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Quantity</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Avg. price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Current price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Value</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">P/L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/60">
          {positions.map((position) => (
            <tr key={position.ticker} className="transition-colors hover:bg-zinc-800/40">
              <td className="px-4 py-3 font-medium text-zinc-100">{position.ticker}</td>
              <td className="px-4 py-3 font-mono text-zinc-300">{position.quantity}</td>
              <td className="px-4 py-3 font-mono text-zinc-300">
                {formatCurrency(position.averagePricePaid, position.currency)}
              </td>
              <td className="px-4 py-3 font-mono text-zinc-300">
                {formatCurrency(position.currentPrice, position.currency)}
              </td>
              <td className="px-4 py-3 font-mono text-zinc-300">
                {formatCurrency(position.currentValue, currency)}
              </td>
              <td
                className={`px-4 py-3 font-mono ${position.unrealizedProfitLoss >= 0 ? "text-emerald-400" : "text-rose-400"}`}
              >
                {formatCurrency(position.unrealizedProfitLoss, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
