// Renders a table of open positions with quantity, prices, value, and P/L.
// Displays an empty state message when no positions are held.

import { formatCurrency } from "../lib/format";
import type { Position } from "../lib/types";

export function PositionsTable({ positions, currency }: { positions: Position[]; currency: string }) {
  if (positions.length === 0) {
    return <p className="text-sm text-neutral-500">No open positions.</p>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-neutral-800">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-neutral-800 bg-neutral-950/40">
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">Ticker</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">Quantity</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Avg. price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Current price
            </th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">Value</th>
            <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">P/L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800/60">
          {positions.map((position) => (
            <tr key={position.ticker} className="transition-colors hover:bg-neutral-800/40">
              <td className="px-4 py-3 font-medium text-neutral-100">{position.ticker}</td>
              <td className="px-4 py-3 text-neutral-300 [font-variant-numeric:tabular-nums]">{position.quantity}</td>
              <td className="px-4 py-3 text-neutral-300 [font-variant-numeric:tabular-nums]">
                {formatCurrency(position.averagePricePaid, position.currency)}
              </td>
              <td className="px-4 py-3 text-neutral-300 [font-variant-numeric:tabular-nums]">
                {formatCurrency(position.currentPrice, position.currency)}
              </td>
              <td className="px-4 py-3 text-neutral-300 [font-variant-numeric:tabular-nums]">
                {formatCurrency(position.currentValue, currency)}
              </td>
              <td
                className={`px-4 py-3 [font-variant-numeric:tabular-nums] ${position.unrealizedProfitLoss > 0 ? "text-[#32e64d]" : position.unrealizedProfitLoss < 0 ? "text-[#ff3b45]" : "text-neutral-100"}`}
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
