import { NextResponse } from "next/server";
import { watchlistBackendRequest } from "../../../../lib/watchlistRoute";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (!query) {
    return NextResponse.json([]);
  }
  return watchlistBackendRequest(`/api/watchlist/search?q=${encodeURIComponent(query)}`);
}
