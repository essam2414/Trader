// Renders a table of open positions with quantity, prices, value, and P/L.
// Displays an empty state message when no positions are held.

import { formatCurrency } from "../lib/format";
import type { Position } from "../lib/types";

export function PositionsTable({ positions, currency }: { positions: Position[]; currency: string }) {
  if (positions.length === 0) {
    return <p className="text-neutral-500">No open positions.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500">
          <th className="py-2">Ticker</th>
          <th className="py-2">Quantity</th>
          <th className="py-2">Avg. price</th>
          <th className="py-2">Current price</th>
          <th className="py-2">Value</th>
          <th className="py-2">P/L</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((position) => (
          <tr key={position.ticker} className="border-b border-neutral-100">
            <td className="py-2 font-medium">{position.ticker}</td>
            <td className="py-2">{position.quantity}</td>
            <td className="py-2">{formatCurrency(position.averagePricePaid, currency)}</td>
            <td className="py-2">{formatCurrency(position.currentPrice, currency)}</td>
            <td className="py-2">{formatCurrency(position.currentValue, currency)}</td>
            <td className={`py-2 ${position.unrealizedProfitLoss >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(position.unrealizedProfitLoss, currency)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
