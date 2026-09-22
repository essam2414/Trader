import { watchlistStreamBackendRequest } from "../../../../lib/watchlistRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return watchlistStreamBackendRequest("/api/watchlist/stream");
}
