import { watchlistBackendRequest } from "../../../../lib/watchlistRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const assetIds = new URL(request.url).searchParams.get("assetIds") ?? "";
  return watchlistBackendRequest(`/api/watchlist/trends/rank?assetIds=${encodeURIComponent(assetIds)}`);
}
