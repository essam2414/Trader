import { getPortfolioCurrent } from "../lib/api";
import { formatCurrency } from "../lib/format";

export async function DashboardAccountSummary() {
  const { account } = await getPortfolioCurrent();
  const unrealizedClassName = account.unrealizedProfitLoss > 0
    ? "text-emerald-400"
    : account.unrealizedProfitLoss < 0
      ? "text-rose-400"
      : "text-neutral-100";

  return (
    <section className="flex h-[72px] items-start gap-10 sm:gap-14" aria-label="Account overview">
      <article className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Total account value</p>
        <p className="mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight text-neutral-100 [font-variant-numeric:tabular-nums]">
          {formatCurrency(account.totalValue, account.currency)}
        </p>
      </article>
      <article className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Unrealised P/L</p>
        <p
          className={`mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight [font-variant-numeric:tabular-nums] ${unrealizedClassName}`}
        >
          {formatCurrency(account.unrealizedProfitLoss, account.currency)}
        </p>
      </article>
    </section>
  );
}

export function DashboardAccountSummarySkeleton() {
  return (
    <section className="flex h-[72px] items-start gap-10 sm:gap-14" aria-busy="true" aria-label="Loading account overview">
      {["Total account value", "Unrealised P/L"].map((label) => (
        <article key={label} className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">{label}</p>
          <div className="mt-2 h-9 w-40 animate-pulse rounded bg-neutral-800" />
        </article>
      ))}
      <span className="sr-only" role="status">Loading account overview</span>
    </section>
  );
}
