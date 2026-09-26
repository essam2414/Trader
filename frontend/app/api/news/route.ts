import { watchlistBackendRequest } from "../../../lib/watchlistRoute";

export async function GET() {
  return watchlistBackendRequest("/api/news");
}

export async function POST() {
  return watchlistBackendRequest("/api/news/refresh", { method: "POST" });
}
