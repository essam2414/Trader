import { watchlistBackendRequest } from "../../../../../lib/watchlistRoute";

export async function GET() {
  return watchlistBackendRequest("/api/watchlist/trends/preferences");
}

export async function PUT(request: Request) {
  const initializeOnly = new URL(request.url).searchParams.get("initializeOnly") === "true";
  return watchlistBackendRequest(`/api/watchlist/trends/preferences${initializeOnly ? "?initializeOnly=true" : ""}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
