// Renders a table of individual closed trades (entry/exit price, quantity,
// dates, P/L, holding period), newest first. Displays an empty state
// message when there are no closed trades.

import { formatCurrency } from "../lib/format";
import type { Trade } from "../lib/types";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

function formatHoldingPeriod(hours: number): string {
  return `${(hours / 24).toFixed(1)}d`;
}

export function TradeHistoryTable({ trades, currency }: { trades: Trade[]; currency: string }) {
  if (trades.length === 0) {
    return <p className="text-neutral-500">No closed trades yet.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500">
          <th className="py-2">Ticker</th>
          <th className="py-2">Entry date</th>
          <th className="py-2">Entry price</th>
          <th className="py-2">Exit date</th>
          <th className="py-2">Exit price</th>
          <th className="py-2">Quantity</th>
          <th className="py-2">Held</th>
          <th className="py-2">P/L</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((trade, index) => (
          <tr
            key={`${trade.ticker}-${trade.entryAt}-${trade.exitAt}-${index}`}
            className="border-b border-neutral-100"
          >
            <td className="py-2 font-medium">{trade.ticker}</td>
            <td className="py-2">{formatDate(trade.entryAt)}</td>
            <td className="py-2">{formatCurrency(trade.entryPrice, currency)}</td>
            <td className="py-2">{formatDate(trade.exitAt)}</td>
            <td className="py-2">{formatCurrency(trade.exitPrice, currency)}</td>
            <td className="py-2">{trade.quantity}</td>
            <td className="py-2">{formatHoldingPeriod(trade.holdingPeriodHours)}</td>
            <td className={`py-2 ${trade.pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
              {formatCurrency(trade.pnl, currency)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
