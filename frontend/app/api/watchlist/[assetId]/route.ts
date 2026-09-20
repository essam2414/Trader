import { watchlistBackendRequest } from "../../../../lib/watchlistRoute";

export async function DELETE(_: Request, { params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return watchlistBackendRequest(`/api/watchlist/${encodeURIComponent(assetId)}`, { method: "DELETE" });
}
