import { Suspense } from "react";

export const dynamic = "force-dynamic";

import { PortfolioAutoRefresh } from "../components/PortfolioAutoRefresh";
import { PortfolioOverview, PortfolioOverviewSkeleton } from "../components/PortfolioOverview";

export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <PortfolioAutoRefresh />
      <header className="flex items-baseline gap-3">
        <span className="h-2 w-2 rounded-full bg-neutral-100" aria-hidden="true" />
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-100">Portfolio overview</h1>
      </header>

      <Suspense fallback={<PortfolioOverviewSkeleton />}>
        <PortfolioOverview />
      </Suspense>
    </main>
  );
}
