import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Hosted demo: give each browser a visitor id on its first page load, before the
// page's parallel /api calls go out, so they all land in one sandbox
// (server/sandbox.py). The server ignores the cookie outside demo mode.
const COOKIE = "dt_visitor";

function newVisitorId(): string {
  return "v-" + crypto.randomUUID().replaceAll("-", "");
}

export function proxy(request: NextRequest) {
  const res = NextResponse.next();
  if (!/^v-[0-9a-f]{32}$/.test(request.cookies.get(COOKIE)?.value ?? "")) {
    res.cookies.set(COOKIE, newVisitorId(), {
      httpOnly: true,
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
  return res;
}

export const config = {
  // Pages only: not /api (the server handles direct calls), assets or Next internals.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.[a-z0-9]+$).*)"],
};
