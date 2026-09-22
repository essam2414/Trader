import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE, isAuthenticated } from "./auth";
import { backendRequest } from "./api";

export async function authenticatedBackendRequest(
  path: string,
  init: RequestInit = {},
  unavailableMessage = "Service is unavailable",
): Promise<NextResponse> {
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
    return NextResponse.json({ message: unavailableMessage }, { status: 502 });
  }
}

export function watchlistBackendRequest(path: string, init: RequestInit = {}): Promise<NextResponse> {
  return authenticatedBackendRequest(path, init, "Watchlist service is unavailable");
}

export async function watchlistStreamBackendRequest(path: string): Promise<NextResponse> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!(await isAuthenticated(token))) {
    return NextResponse.json({ message: "Unauthenticated" }, { status: 401 });
  }

  try {
    const response = await backendRequest(path, { headers: { Accept: "text/event-stream" } });
    if (!response.ok || !response.body) {
      const body: unknown = await response.json().catch(() => ({ message: "Watchlist stream unavailable" }));
      return NextResponse.json(body, { status: response.status || 502 });
    }
    const headers = new Headers({
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "Content-Type": "text/event-stream",
      "X-Accel-Buffering": "no",
    });
    return new NextResponse(response.body, { status: response.status, headers });
  } catch {
    return NextResponse.json({ message: "Watchlist stream unavailable" }, { status: 502 });
  }
}

export async function watchlistLogoBackendRequest(path: string): Promise<NextResponse> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!(await isAuthenticated(token))) {
    return new NextResponse(null, { status: 401 });
  }

  try {
    const response = await backendRequest(path);
    const headers = new Headers();
    const contentType = response.headers.get("content-type");
    const cacheControl = response.headers.get("cache-control");
    if (contentType) headers.set("Content-Type", contentType);
    if (cacheControl) headers.set("Cache-Control", cacheControl);
    return new NextResponse(response.body, { status: response.status, headers });
  } catch {
    return new NextResponse(null, { status: 502 });
  }
}
