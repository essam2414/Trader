import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE, isAuthenticated } from "./auth";
import { backendRequest } from "./api";

export async function watchlistBackendRequest(path: string, init: RequestInit = {}): Promise<NextResponse> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!(await isAuthenticated(token))) {
    return NextResponse.json({ message: "Unauthenticated" }, { status: 401 });
  }

  try {
    const response = await backendRequest(path, init);
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }
    const body: unknown = await response.json().catch(() => ({ message: "Invalid backend response" }));
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ message: "Watchlist service is unavailable" }, { status: 502 });
  }
}
