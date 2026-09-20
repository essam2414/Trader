import { Suspense } from "react";
import { PortfolioAutoRefresh } from "../../components/PortfolioAutoRefresh";
import { DashboardAccountSummary, DashboardAccountSummarySkeleton } from "../../components/DashboardAccountSummary";
import { WatchlistSection } from "../../components/WatchlistSection";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <PortfolioAutoRefresh />
      <Suspense fallback={<DashboardAccountSummarySkeleton />}>
        <DashboardAccountSummary />
      </Suspense>
      <WatchlistSection />
    </main>
  );
}
