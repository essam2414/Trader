import { watchlistBackendRequest } from "../../../../../lib/watchlistRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return watchlistBackendRequest(`/api/watchlist/${encodeURIComponent(assetId)}/analysis`);
}
