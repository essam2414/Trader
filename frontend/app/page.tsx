// Main dashboard Server Component: fetches live portfolio data from the backend API
// server-side (so BACKEND_URL/DASHBOARD_API_KEY never reach the browser) and renders
// the summary, equity curve, and positions table.
import { EquityCurveChart } from "../components/EquityCurveChart";
import { PortfolioSummary } from "../components/PortfolioSummary";
import { PositionsTable } from "../components/PositionsTable";
import { getPortfolioCurrent, getPortfolioHistory } from "../lib/api";

export default async function DashboardPage() {
  const [current, history] = await Promise.all([getPortfolioCurrent(), getPortfolioHistory()]);

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <h1 className="text-3xl font-bold">Portfolio dashboard</h1>
      <PortfolioSummary account={current.account} />
      <section>
        <h2 className="mb-4 text-xl font-semibold">Value over time</h2>
        <EquityCurveChart snapshots={history} />
      </section>
      <section>
        <h2 className="mb-4 text-xl font-semibold">Open positions</h2>
        <PositionsTable positions={current.positions} currency={current.account.currency} />
      </section>
    </main>
  );
}
