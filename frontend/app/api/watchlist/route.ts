import { watchlistBackendRequest } from "../../../lib/watchlistRoute";

export async function GET() {
  return watchlistBackendRequest("/api/watchlist");
}

export async function POST(request: Request) {
  const body = await request.text();
  return watchlistBackendRequest("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
