// Renders the account-level realized P/L summary.

import { formatCurrency } from "../lib/format";
import type { AccountSummary } from "../lib/types";

export function PortfolioSummary({ account }: { account: AccountSummary }) {
  const realizedClassName = account.realizedProfitLoss > 0
    ? "text-[#32e64d]"
    : account.realizedProfitLoss < 0
      ? "text-[#ff3b45]"
      : "text-neutral-100";

  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Realized P/L</p>
      <p
        className={`mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight [font-variant-numeric:tabular-nums] ${realizedClassName}`}
      >
        {formatCurrency(Math.abs(account.realizedProfitLoss), account.currency)}
      </p>
    </div>
  );
}
