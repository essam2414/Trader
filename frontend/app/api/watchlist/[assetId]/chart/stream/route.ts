import { watchlistStreamBackendRequest } from "../../../../../../lib/watchlistRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return watchlistStreamBackendRequest(`/api/watchlist/${encodeURIComponent(assetId)}/chart/stream`);
}
