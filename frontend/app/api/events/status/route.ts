import { watchlistBackendRequest } from "../../../../lib/watchlistRoute";

export async function GET() {
  return watchlistBackendRequest("/api/events/status");
}
