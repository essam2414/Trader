// Renders account-level summary stat tiles: total value, cash available, unrealized P/L, and realized P/L.
// These metrics provide an at-a-glance view of the portfolio's current state.

import { formatCurrency } from "../lib/format";
import type { AccountSummary } from "../lib/types";

export function PortfolioSummary({ account }: { account: AccountSummary }) {
  const isUnrealizedProfit = account.unrealizedProfitLoss >= 0;
  const isRealizedProfit = account.realizedProfitLoss >= 0;
  return (
    <div className="grid grid-cols-2 divide-x divide-y divide-zinc-800 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 sm:grid-cols-4 sm:divide-y-0">
      <div className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Total value</p>
        <p className="mt-1 font-mono text-2xl font-semibold text-zinc-100">
          {formatCurrency(account.totalValue, account.currency)}
        </p>
      </div>
      <div className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Cash available</p>
        <p className="mt-1 font-mono text-2xl font-semibold text-zinc-100">
          {formatCurrency(account.cash.availableToTrade, account.currency)}
        </p>
      </div>
      <div className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Unrealized P/L</p>
        <p
          className={`mt-1 font-mono text-2xl font-semibold ${isUnrealizedProfit ? "text-emerald-400" : "text-rose-400"}`}
        >
          {formatCurrency(account.unrealizedProfitLoss, account.currency)}
        </p>
      </div>
      <div className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Realized P/L</p>
        <p
          className={`mt-1 font-mono text-2xl font-semibold ${isRealizedProfit ? "text-emerald-400" : "text-rose-400"}`}
        >
          {formatCurrency(account.realizedProfitLoss, account.currency)}
        </p>
      </div>
    </div>
  );
}
