import { watchlistStreamBackendRequest } from "../../../../../lib/watchlistRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const assetIds = new URL(request.url).searchParams.get("assetIds") ?? "";
  return watchlistStreamBackendRequest(`/api/watchlist/charts/stream?assetIds=${encodeURIComponent(assetIds)}`);
}
