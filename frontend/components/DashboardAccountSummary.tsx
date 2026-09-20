import { getPortfolioCurrent } from "../lib/api";
import { formatCurrency } from "../lib/format";

export async function DashboardAccountSummary() {
  const { account } = await getPortfolioCurrent();
  const isUnrealizedProfit = account.unrealizedProfitLoss >= 0;

  return (
    <section className="grid grid-cols-2 gap-5" aria-label="Account overview">
      <article className="rounded-xl border border-neutral-800 bg-neutral-900 p-5 shadow-lg shadow-black/10">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Total account value</p>
        <p className="mt-2 font-mono text-4xl font-semibold tracking-tight text-neutral-100">
          {formatCurrency(account.totalValue, account.currency)}
        </p>
      </article>
      <article className="rounded-xl border border-neutral-800 bg-neutral-900 p-5 shadow-lg shadow-black/10">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Unrealised P/L</p>
        <p
          className={`mt-2 font-mono text-4xl font-semibold tracking-tight ${
            isUnrealizedProfit ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {formatCurrency(account.unrealizedProfitLoss, account.currency)}
        </p>
      </article>
    </section>
  );
}

export function DashboardAccountSummarySkeleton() {
  return (
    <section className="grid grid-cols-2 gap-5" aria-busy="true" aria-label="Loading account overview">
      {["Total account value", "Unrealised P/L"].map((label) => (
        <article key={label} className="rounded-xl border border-neutral-800 bg-neutral-900 p-5 shadow-lg shadow-black/10">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">{label}</p>
          <div className="mt-3 h-10 w-48 animate-pulse rounded bg-neutral-800" />
        </article>
      ))}
      <span className="sr-only" role="status">Loading account overview</span>
    </section>
  );
}
