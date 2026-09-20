import { PortfolioAutoRefresh } from "../../components/PortfolioAutoRefresh";
import { getPortfolioCurrent } from "../../lib/api";
import { formatCurrency } from "../../lib/format";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const { account } = await getPortfolioCurrent();
  const isUnrealizedProfit = account.unrealizedProfitLoss >= 0;

  return (
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <PortfolioAutoRefresh />
      <header className="flex items-end justify-between gap-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-500">Account snapshot</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-neutral-100">Dashboard</h1>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-xs font-medium text-neutral-300">
          <span className="h-1.5 w-1.5 rounded-full bg-neutral-400" aria-hidden="true" />
          Live data
        </div>
      </header>

      <section className="grid grid-cols-2 gap-5" aria-label="Account overview">
        <article className="rounded-xl border border-neutral-800 bg-neutral-900 p-7 shadow-lg shadow-black/10">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Total account value</p>
          <p className="mt-3 font-mono text-4xl font-semibold tracking-tight text-neutral-100">
            {formatCurrency(account.totalValue, account.currency)}
          </p>
          <p className="mt-5 text-sm text-neutral-500">Current value of your account</p>
        </article>
        <article className="rounded-xl border border-neutral-800 bg-neutral-900 p-7 shadow-lg shadow-black/10">
          <div className="flex items-start justify-between gap-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Unrealised P/L</p>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${isUnrealizedProfit ? "bg-emerald-400/10 text-emerald-300" : "bg-rose-400/10 text-rose-300"}`}>
              {isUnrealizedProfit ? "Gain" : "Loss"}
            </span>
          </div>
          <p
            className={`mt-3 font-mono text-4xl font-semibold tracking-tight ${
              isUnrealizedProfit ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {formatCurrency(account.unrealizedProfitLoss, account.currency)}
          </p>
          <p className="mt-5 text-sm text-neutral-500">Open-position performance</p>
        </article>
      </section>

      <p className="text-xs text-neutral-500">Values refresh automatically every five seconds while this page is open.</p>
    </main>
  );
}
