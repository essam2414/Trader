// Renders account-level summary stat tiles: total value, cash available, unrealized P/L, and realized P/L.
// These metrics provide an at-a-glance view of the portfolio's current state.

import { formatCurrency } from "../lib/format";
import type { AccountSummary } from "../lib/types";

export function PortfolioSummary({ account }: { account: AccountSummary }) {
  const isProfit = account.unrealizedProfitLoss >= 0;
  return (
    <div className="grid grid-cols-2 gap-4 rounded-lg border border-neutral-200 p-6 sm:grid-cols-4">
      <div>
        <p className="text-sm text-neutral-500">Total value</p>
        <p className="text-2xl font-semibold">{formatCurrency(account.totalValue, account.currency)}</p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Cash available</p>
        <p className="text-2xl font-semibold">
          {formatCurrency(account.cash.availableToTrade, account.currency)}
        </p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Unrealized P/L</p>
        <p className={`text-2xl font-semibold ${isProfit ? "text-green-600" : "text-red-600"}`}>
          {formatCurrency(account.unrealizedProfitLoss, account.currency)}
        </p>
      </div>
      <div>
        <p className="text-sm text-neutral-500">Realized P/L</p>
        <p className="text-2xl font-semibold">{formatCurrency(account.realizedProfitLoss, account.currency)}</p>
      </div>
    </div>
  );
}
