import { watchlistBackendRequest } from "../../../../lib/watchlistRoute";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    return Response.json({ detail: "Invalid news story" }, { status: 400 });
  }
  return watchlistBackendRequest(`/api/news/${id}`);
}
