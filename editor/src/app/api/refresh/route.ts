import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import {
  REFRESH_COOKIE,
  REFRESH_MAX_AGE_SECONDS,
  engineBaseUrl,
  refreshCookieOptions,
} from '@/lib/engine';

/**
 * Trades the refresh cookie for a new access token, and rotates the cookie.
 *
 * The engine revokes the presented refresh token as it issues the new pair, so a stolen token and
 * the real one cannot both keep working. That only holds if the new one actually replaces the old
 * cookie here — a handler that returned the access token and forgot to re-set the cookie would
 * leave the browser holding a token the engine has already revoked, and the next refresh would log
 * the user out for no visible reason.
 */
export async function POST(): Promise<NextResponse> {
  const jar = await cookies();
  const refreshToken = jar.get(REFRESH_COOKIE)?.value;

  if (!refreshToken) {
    return NextResponse.json({ error: 'no session' }, { status: 401 });
  }

  const engineResponse = await fetch(`${engineBaseUrl()}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
    cache: 'no-store',
  });

  if (!engineResponse.ok) {
    // The cookie is cleared as well as refused. Leaving a token the engine has rejected in the
    // browser means every subsequent request makes the same doomed round trip.
    const refused = NextResponse.json({ error: 'that session has expired' }, { status: 401 });
    refused.cookies.set(REFRESH_COOKIE, '', refreshCookieOptions(0));
    return refused;
  }

  const tokens = (await engineResponse.json()) as {
    accessToken?: string;
    refreshToken?: string;
  };
  if (!tokens.accessToken || !tokens.refreshToken) {
    return NextResponse.json({ error: 'the engine returned an unusable session' }, { status: 502 });
  }

  const response = NextResponse.json({ accessToken: tokens.accessToken });
  response.cookies.set(
    REFRESH_COOKIE,
    tokens.refreshToken,
    refreshCookieOptions(REFRESH_MAX_AGE_SECONDS),
  );
  return response;
}
