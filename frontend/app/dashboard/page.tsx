import { Suspense } from "react";
import { PortfolioAutoRefresh } from "../../components/PortfolioAutoRefresh";
import { DashboardAccountSummary, DashboardAccountSummarySkeleton } from "../../components/DashboardAccountSummary";
import { NewsSection } from "../../components/NewsSection";
import { WatchlistSection } from "../../components/WatchlistSection";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return (
    <main className="w-full">
      <PortfolioAutoRefresh />
      <div className="mx-auto w-full max-w-[1440px] px-6 pb-8 pt-6 xl:px-8 xl:pb-8 xl:pt-8">
        <Suspense fallback={<DashboardAccountSummarySkeleton />}>
          <DashboardAccountSummary />
        </Suspense>
      </div>
      <div className="border-t border-neutral-800">
        <div className="relative mx-auto grid w-full max-w-[1440px] grid-cols-1 gap-8 px-6 min-[1180px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] min-[1180px]:after:absolute min-[1180px]:after:inset-y-0 min-[1180px]:after:left-1/2 min-[1180px]:after:w-px min-[1180px]:after:bg-neutral-800 min-[1180px]:after:content-[''] xl:px-8">
          <WatchlistSection />
          <NewsSection />
        </div>
      </div>
    </main>
  );
}
