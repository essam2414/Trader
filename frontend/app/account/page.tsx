import { Suspense } from "react";
import { PortfolioAutoRefresh } from "../../components/PortfolioAutoRefresh";
import { PortfolioOverview, PortfolioOverviewSkeleton } from "../../components/PortfolioOverview";

export const dynamic = "force-dynamic";

export default function AccountPage() {
  return (
    <main className="mx-auto w-full max-w-[1440px] space-y-6 px-6 py-8 xl:px-8 xl:py-10">
      <PortfolioAutoRefresh />

      <Suspense fallback={<PortfolioOverviewSkeleton />}>
        <PortfolioOverview />
      </Suspense>
    </main>
  );
}
