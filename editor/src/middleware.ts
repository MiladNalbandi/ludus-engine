import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { REFRESH_COOKIE } from '@/lib/engine';

/**
 * A convenience redirect, and nothing more.
 *
 * This is **not** a security control and must never be treated as one. It checks only whether a
 * refresh cookie is present — not whether it is valid, unexpired or unrevoked, none of which can be
 * known without asking the engine. Its whole job is to send someone with no session to the login
 * page instead of showing them a page that will fail to load.
 *
 * The engine is the security control. Every route that matters is authorised there, against the
 * token, on every request. The predecessor codebase had a middleware like this one exempting
 * `/api/*` on the grounds that "they have their own auth" — and some of those routes had none at
 * all, which is how unauthenticated writes shipped.
 */
export function middleware(request: NextRequest): NextResponse {
  const hasCookie = request.cookies.has(REFRESH_COOKIE);
  if (!hasCookie && !request.nextUrl.pathname.startsWith('/login')) {
    return NextResponse.redirect(new URL('/login', request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Pages only. The API routes are deliberately excluded, because the login and refresh handlers
  // have to be reachable without a session -- and because a redirect is a useless answer to a
  // fetch. They authorise themselves: /api/refresh requires the cookie, and everything under
  // /api/engine is authorised by the engine.
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
