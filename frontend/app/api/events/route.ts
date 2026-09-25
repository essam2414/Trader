import { watchlistBackendRequest } from "../../../lib/watchlistRoute";

export async function GET() {
  return watchlistBackendRequest("/api/events");
}

export async function POST() {
  return watchlistBackendRequest("/api/events/refresh", { method: "POST" });
}
