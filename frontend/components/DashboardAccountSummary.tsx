import { getPortfolioCurrent } from "../lib/api";
import { LiveDashboardAccountSummary } from "./LiveDashboardAccountSummary";

export async function DashboardAccountSummary() {
  const { account } = await getPortfolioCurrent();
  return <LiveDashboardAccountSummary initialAccount={account} />;
}

export function DashboardAccountSummarySkeleton() {
  return (
    <section className="flex h-[72px] items-start gap-10 sm:gap-14" aria-busy="true" aria-label="Loading account overview">
      {["Total account value", "Unrealised P/L", "Weekly gain"].map((label) => (
        <article key={label} className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">{label}</p>
          <div className="mt-2 h-9 w-40 animate-pulse rounded bg-neutral-800" />
        </article>
      ))}
      <span className="sr-only" role="status">Loading account overview</span>
    </section>
  );
}
