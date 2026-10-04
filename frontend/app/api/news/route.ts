import { watchlistBackendRequest } from "../../../lib/watchlistRoute";

export async function GET(request: Request) {
  const incoming = new URL(request.url).searchParams;
  const query = new URLSearchParams();
  for (const key of ["assetId", "limit", "offset"]) {
    const value = incoming.get(key);
    if (value !== null) query.set(key, value);
  }
  return watchlistBackendRequest(`/api/news${query.size ? `?${query}` : ""}`);
}

export async function POST() {
  return watchlistBackendRequest("/api/news/refresh", { method: "POST" });
}
