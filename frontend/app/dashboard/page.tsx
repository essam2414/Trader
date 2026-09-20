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
    </main>
  );
}
