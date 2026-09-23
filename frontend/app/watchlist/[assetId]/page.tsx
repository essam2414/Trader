import { StockPriceChart } from "../../../components/StockPriceChart";

export const dynamic = "force-dynamic";

export default async function WatchlistStockPage({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return (
    <main className="min-h-screen w-full bg-[#050505] px-5 py-6 sm:px-8 sm:py-8 lg:px-10">
      <StockPriceChart assetId={assetId} />
    </main>
  );
}
