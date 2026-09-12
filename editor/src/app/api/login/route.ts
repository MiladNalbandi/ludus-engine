import { NextResponse } from 'next/server';
import {
  REFRESH_COOKIE,
  REFRESH_MAX_AGE_SECONDS,
  engineBaseUrl,
  refreshCookieOptions,
} from '@/lib/engine';

/**
 * Exchanges an email address and password for a session.
 *
 * The split is the whole point: the refresh token goes into an httpOnly cookie that page
 * JavaScript cannot read, and the access token comes back in the body for the store to hold in
 * memory. A token in `localStorage` is readable by any script that gets onto the page, and one
 * cross-site scripting hole then becomes a stolen session that outlives the tab.
 *
 * The credentials are forwarded and never stored, logged, or echoed back.
 */
export async function POST(request: Request): Promise<NextResponse> {
  let body: { email?: unknown; password?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'expected a JSON body' }, { status: 400 });
  }

  if (typeof body.email !== 'string' || typeof body.password !== 'string') {
    return NextResponse.json({ error: 'email and password are required' }, { status: 400 });
  }

  const engineResponse = await fetch(`${engineBaseUrl()}/api/v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: body.email, password: body.password }),
    cache: 'no-store',
  });

  if (!engineResponse.ok) {
    // The engine answers every authentication failure identically, on purpose: telling an unknown
    // address apart from a wrong password turns a login form into a list of who has an account.
    // Passing its status and nothing else through keeps that true here.
    return NextResponse.json({ error: 'those credentials were not accepted' }, { status: 401 });
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
