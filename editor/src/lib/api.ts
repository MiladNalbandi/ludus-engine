import { session } from '@/stores/session';

/**
 * Every call the browser makes to the engine.
 *
 * Two rules, and the second is the one that is easy to get wrong.
 *
 * The bearer token is attached from the in-memory store. And a `401` triggers **one** refresh and
 * **one** retry — never a loop. A wrapper that refreshes on every `401` without counting turns an
 * expired refresh token into an infinite pair of requests hammering the engine, and the symptom is
 * a hung page rather than a login prompt.
 *
 * Concurrent calls share a single refresh. Without that, ten requests arriving after an expiry all
 * refresh, and because the engine revokes each refresh token as it issues the next, nine of those
 * ten present a token that has just been revoked and the session dies. That is the subtle failure
 * this design exists to avoid, and it only appears under concurrency.
 */
const ENGINE_PREFIX = '/api/engine';

export class NotSignedIn extends Error {
  constructor() {
    super('the session has expired');
    this.name = 'NotSignedIn';
  }
}

/** The refresh in flight, if any, so that concurrent callers wait on one rather than racing. */
let refreshInFlight: Promise<string | null> | null = null;

async function refreshOnce(): Promise<string | null> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch('/api/refresh', { method: 'POST' });
      if (!response.ok) {
        session.clear();
        return null;
      }
      const body = (await response.json()) as { accessToken?: string };
      if (!body.accessToken) {
        session.clear();
        return null;
      }
      session.set(body.accessToken);
      return body.accessToken;
    } finally {
      // Cleared whatever happened, so the next expiry refreshes again rather than reusing a
      // settled promise that resolved to null.
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

function withToken(init: RequestInit, token: string | null): RequestInit {
  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return { ...init, headers };
}

/**
 * Calls an engine path, refreshing once if the token has expired.
 *
 * @param path an engine path such as `/api/v1/admin/waves`
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = `${ENGINE_PREFIX}${path}`;

  const first = await fetch(url, withToken(init, session.token()));
  if (first.status !== 401) {
    return first;
  }

  const refreshed = await refreshOnce();
  if (!refreshed) {
    throw new NotSignedIn();
  }

  const second = await fetch(url, withToken(init, refreshed));
  if (second.status === 401) {
    // A 401 with a token minted seconds ago is not an expiry. Retrying again would be a loop.
    session.clear();
    throw new NotSignedIn();
  }
  return second;
}

/** `apiFetch` plus JSON decoding, for the many callers that want exactly that. */
export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new Error(`${init.method ?? 'GET'} ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Exchanges credentials for a session. The refresh token never reaches this code. */
export async function signIn(email: string, password: string): Promise<void> {
  const response = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error('those credentials were not accepted');
  }
  const body = (await response.json()) as { accessToken?: string };
  if (!body.accessToken) {
    throw new Error('the engine returned an unusable session');
  }
  session.set(body.accessToken);
}

export async function signOut(): Promise<void> {
  await fetch('/api/logout', { method: 'POST' });
  session.clear();
}

/** Restores a session on a fresh page load, using the httpOnly cookie. */
export async function restoreSession(): Promise<boolean> {
  return (await refreshOnce()) !== null;
}
