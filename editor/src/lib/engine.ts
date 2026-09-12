/**
 * Where the engine is, read on the server only.
 *
 * Deliberately not a `NEXT_PUBLIC_` variable. The browser never talks to the engine directly:
 * every call goes through this app's own route handlers, which is what lets the refresh token live
 * in an httpOnly cookie and lets a self-hosted deployment leave the engine unpublished entirely,
 * reachable only on the compose network. A public variable would be inlined into the browser
 * bundle and would invite someone to "simplify" the proxy away, taking both of those with it.
 */
export function engineBaseUrl(): string {
  const url = process.env.LUDUS_ENGINE_URL;
  if (!url) {
    throw new Error(
      'LUDUS_ENGINE_URL is not set. The editor has no default, because an editor pointed at the ' +
        'wrong engine writes content into the wrong database.',
    );
  }
  return url.replace(/\/+$/, '');
}

/** The cookie carrying the refresh token. Never read by page JavaScript; it cannot be. */
export const REFRESH_COOKIE = 'ludus_refresh';

/**
 * `secure` is off only when the app is served over plain HTTP, which for a self-hosted editor on
 * localhost is the normal case. A `Secure` cookie is silently dropped there, and silently dropped
 * means "you are logged out again" with nothing in any log.
 */
export function refreshCookieOptions(maxAgeSeconds: number) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: process.env.LUDUS_EDITOR_HTTPS === 'true',
    path: '/',
    maxAge: maxAgeSeconds,
  };
}

/** Thirty days, matching the engine's own default refresh lifetime. */
export const REFRESH_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;
