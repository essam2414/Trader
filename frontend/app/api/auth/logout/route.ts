import { NextResponse } from "next/server";
import { AUTH_COOKIE } from "../../../../lib/auth";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(AUTH_COOKIE);
  response.headers.set("Clear-Site-Data", "\"cache\"");
  return response;
}
