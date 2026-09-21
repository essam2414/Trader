import { authenticatedBackendRequest } from "../../../../lib/watchlistRoute";

export async function GET() {
  return authenticatedBackendRequest("/api/portfolio/current", {}, "Portfolio service is unavailable");
}
