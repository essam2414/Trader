import { watchlistLogoBackendRequest } from "../../../../../lib/watchlistRoute";

export async function GET(_: Request, { params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return watchlistLogoBackendRequest(`/api/watchlist/${encodeURIComponent(assetId)}/logo`);
}
