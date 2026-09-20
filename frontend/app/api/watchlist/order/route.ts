import { watchlistBackendRequest } from "../../../../lib/watchlistRoute";

export async function PUT(request: Request) {
  const body = await request.text();
  return watchlistBackendRequest("/api/watchlist/order", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
