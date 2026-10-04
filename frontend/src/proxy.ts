import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only (cookie present or not) — the (app) layout does the
// real DB-backed session lookup. Logged-in users are bounced off /login and
// /signup by those pages themselves, so a stale cookie can't cause a loop.
// Must match SESSION_COOKIE in lib/auth/session.ts; not imported to keep
// Prisma/node:crypto out of the proxy bundle.
const SESSION_COOKIE = "aqp_session";

const PROTECTED = ["/dashboard", "/projects", "/reports", "/runs", "/settings", "/test-cases"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  if (!hasSession && PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
