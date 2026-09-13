import { NextResponse } from 'next/server';
import { REFRESH_COOKIE, refreshCookieOptions } from '@/lib/engine';

/**
 * Clears the refresh cookie.
 *
 * The access token is not revoked, because it cannot be — it is verified by checking a signature
 * and nothing else, which is what makes it fast. Signing out therefore stops the session from being
 * renewed rather than killing it instantly, and the access token's lifetime is how long that gap
 * lasts. That is a property of the engine's token design, not something this route can improve.
 */
export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(REFRESH_COOKIE, '', refreshCookieOptions(0));
  return response;
}
