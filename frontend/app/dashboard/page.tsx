import { Suspense } from "react";
import { DashboardAccountSummary, DashboardAccountSummarySkeleton } from "../../components/DashboardAccountSummary";
import { NewsSection } from "../../components/NewsSection";
import { WatchlistSection } from "../../components/WatchlistSection";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return (
    <main className="flex h-screen min-h-0 w-full flex-col overflow-hidden">
      <div className="mx-auto w-full max-w-[1440px] shrink-0 px-6 pb-8 pt-6 xl:px-8 xl:pb-8 xl:pt-8">
        <Suspense fallback={<DashboardAccountSummarySkeleton />}>
          <DashboardAccountSummary />
        </Suspense>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden border-t border-neutral-800">
        <div className="relative mx-auto grid h-full min-h-0 w-full max-w-[1440px] grid-cols-[minmax(0,9fr)_minmax(0,11fr)] gap-8 pl-6 pr-2 after:absolute after:inset-y-0 after:left-[45%] after:w-px after:bg-neutral-800 after:content-[''] xl:pl-8 xl:pr-3">
          <WatchlistSection />
          <NewsSection />
        </div>
      </div>
    </main>
  );
}
