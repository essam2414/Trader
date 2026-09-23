import { watchlistBackendRequest } from "../../../../../lib/watchlistRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  const range = new URL(request.url).searchParams.get("range") ?? "1D";
  return watchlistBackendRequest(`/api/watchlist/${encodeURIComponent(assetId)}/chart?range=${encodeURIComponent(range)}`);
}
