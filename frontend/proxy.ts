import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, isAuthenticated } from "./lib/auth";

export async function proxy(request: NextRequest) {
  const isLoggedIn = await isAuthenticated(request.cookies.get(AUTH_COOKIE)?.value);
  const loginUrl = new URL("/login", request.url);

  if (request.nextUrl.pathname === "/login") {
    if (isLoggedIn) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }

    const response = NextResponse.next();
    response.headers.set("Cache-Control", "no-store, max-age=0");
    return response;
  }

  if (!isLoggedIn) {
    return NextResponse.redirect(loginUrl);
  }

  const response = NextResponse.next();
  response.headers.set("Cache-Control", "no-store, max-age=0");
  return response;
}

export const config = {
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
};
