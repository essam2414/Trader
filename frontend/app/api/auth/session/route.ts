import { NextResponse } from "next/server";
import { AUTH_COOKIE, isAuthenticated } from "../../../../lib/auth";

export async function GET(request: Request) {
  const cookie = request.headers.get("cookie") ?? "";
  const token = cookie.match(new RegExp(`(?:^|;\\s*)${AUTH_COOKIE}=([^;]+)`))?.[1];
  const authenticated = await isAuthenticated(token);

  return NextResponse.json(
    { authenticated },
    {
      status: authenticated ? 200 : 401,
      headers: { "Cache-Control": "no-store, max-age=0" },
    },
  );
}
