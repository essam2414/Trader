import { NextResponse } from "next/server";
import { AUTH_COOKIE, createSessionToken, isValidPin, SESSION_DURATION_SECONDS } from "../../../../lib/auth";

export async function POST(request: Request) {
  const body: unknown = await request.json().catch(() => null);
  const pin = typeof body === "object" && body !== null && "pin" in body ? body.pin : undefined;

  if (!isValidPin(pin)) {
    return NextResponse.json({ message: "Incorrect PIN." }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: AUTH_COOKIE,
    value: await createSessionToken(),
    httpOnly: true,
    maxAge: SESSION_DURATION_SECONDS,
    path: "/",
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  return response;
}
