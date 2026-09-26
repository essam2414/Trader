// Renders the account-level realized P/L and cumulative closed-trade totals.

import { formatCurrency } from "../lib/format";
import type { AccountSummary } from "../lib/types";

export function PortfolioSummary({
  account,
  totalWinningTradePnl,
  totalLosingTradePnl,
}: {
  account: AccountSummary;
  totalWinningTradePnl: number;
  totalLosingTradePnl: number;
}) {
  const realizedClassName = account.realizedProfitLoss > 0
    ? "text-[#32e64d]"
    : account.realizedProfitLoss < 0
      ? "text-[#ff3b45]"
      : "text-neutral-100";

  return (
    <section className="flex flex-col items-start gap-y-6" aria-label="Trade outcome summary">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Realized P/L</p>
        <p
          className={`mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight [font-variant-numeric:tabular-nums] ${realizedClassName}`}
        >
          {formatCurrency(Math.abs(account.realizedProfitLoss), account.currency)}
        </p>
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Good trades</p>
        <p className="mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight text-[#32e64d] [font-variant-numeric:tabular-nums]">
          {formatCurrency(totalWinningTradePnl, account.currency)}
        </p>
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Bad trades</p>
        <p className="mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight text-[#ff3b45] [font-variant-numeric:tabular-nums]">
          {formatCurrency(totalLosingTradePnl, account.currency)}
        </p>
      </div>
    </section>
  );
}
