import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotSignedIn, apiFetch, restoreSession, signIn, signOut } from '@/lib/api';
import { session, useSession } from '@/stores/session';

/**
 * The refresh behaviour, which is the only part of this file with any real logic in it.
 *
 * Two of these tests fail against implementations that look perfectly correct on a single request:
 * the one that counts retries, and the one that makes concurrent callers share a refresh. Both
 * failures only appear under conditions a manual click-through never produces.
 */
type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

let calls: { url: string; authorization: string | null }[] = [];

function mockFetch(handler: Handler): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const authorization = new Headers(init?.headers).get('Authorization');
      calls.push({ url, authorization });
      return handler(url, init);
    }),
  );
}

beforeEach(() => {
  calls = [];
  useSession.setState({ accessToken: null, status: 'unknown' });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiFetch', () => {
  it('attaches the in-memory access token', async () => {
    session.set('token-one');
    mockFetch(() => json({ ok: true }));

    await apiFetch('/api/v1/admin/waves');

    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toBe('/api/engine/api/v1/admin/waves');
    expect(calls[0]?.authorization).toBe('Bearer token-one');
  });

  it('does not refresh when the first call succeeds', async () => {
    session.set('token-one');
    mockFetch(() => json({ ok: true }));

    await apiFetch('/api/v1/admin/waves');

    expect(calls.map((c) => c.url)).not.toContain('/api/refresh');
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    session.set('expired');
    mockFetch((url) => {
      if (url === '/api/refresh') {
        return json({ accessToken: 'token-two' });
      }
      return calls.filter((c) => c.url.startsWith('/api/engine')).length === 1
        ? json({ error: 'expired' }, 401)
        : json({ ok: true });
    });

    const response = await apiFetch('/api/v1/admin/waves');

    expect(response.status).toBe(200);
    expect(calls.map((c) => c.url)).toEqual([
      '/api/engine/api/v1/admin/waves',
      '/api/refresh',
      '/api/engine/api/v1/admin/waves',
    ]);
    expect(calls[2]?.authorization).toBe('Bearer token-two');
    expect(session.token()).toBe('token-two');
  });

  it('retries exactly once, so an expired refresh token cannot become a loop', async () => {
    session.set('expired');
    // Everything says 401, including the refresh's own retry target.
    mockFetch((url) => (url === '/api/refresh' ? json({ accessToken: 'fresh' }) : json({}, 401)));

    await expect(apiFetch('/api/v1/admin/waves')).rejects.toBeInstanceOf(NotSignedIn);

    const engineCalls = calls.filter((c) => c.url.startsWith('/api/engine'));
    expect(engineCalls).toHaveLength(2);
    expect(calls.filter((c) => c.url === '/api/refresh')).toHaveLength(1);
    expect(session.token()).toBeNull();
  });

  it('gives up without retrying when the refresh itself is refused', async () => {
    session.set('expired');
    mockFetch((url) => (url === '/api/refresh' ? json({}, 401) : json({}, 401)));

    await expect(apiFetch('/api/v1/admin/waves')).rejects.toBeInstanceOf(NotSignedIn);

    expect(calls.filter((c) => c.url.startsWith('/api/engine'))).toHaveLength(1);
    expect(useSession.getState().status).toBe('signed-out');
  });

  it('shares one refresh between concurrent callers', async () => {
    session.set('expired');
    let refreshes = 0;
    mockFetch(async (url) => {
      if (url === '/api/refresh') {
        refreshes += 1;
        // A real refresh is a round trip; without the delay every caller would find it already
        // settled and the race this test exists for would not happen.
        await new Promise((resolve) => setTimeout(resolve, 10));
        return json({ accessToken: `token-${refreshes}` });
      }
      const engineCalls = calls.filter((c) => c.url.startsWith('/api/engine')).length;
      return engineCalls <= 3 ? json({}, 401) : json({ ok: true });
    });

    await Promise.all([
      apiFetch('/api/v1/admin/waves'),
      apiFetch('/api/v1/admin/audio'),
      apiFetch('/api/v1/admin/wave-levels'),
    ]);

    expect(refreshes)
      // The engine revokes each refresh token as it issues the next, so three refreshes would mean
      // two callers presenting a token that had just been revoked -- and a dead session.
      //
      // Verified by breaking it: changing `refreshInFlight ??=` to `refreshInFlight =` leaves the
      // other twelve tests here green and fails only this one.
      .toBe(1);
  });

  it('refreshes again on a later expiry rather than reusing the settled promise', async () => {
    session.set('expired');
    let refreshes = 0;
    mockFetch((url) => {
      if (url === '/api/refresh') {
        refreshes += 1;
        return json({ accessToken: `token-${refreshes}` });
      }
      // Every first attempt fails, so each call has to refresh on its own.
      return calls.filter((c) => c.url.startsWith('/api/engine')).length % 2 === 1
        ? json({}, 401)
        : json({ ok: true });
    });

    await apiFetch('/api/v1/admin/waves');
    await apiFetch('/api/v1/admin/audio');

    expect(refreshes).toBe(2);
  });
});

describe('signIn', () => {
  it('stores the access token and never sees the refresh token', async () => {
    mockFetch(() => json({ accessToken: 'token-one' }));

    await signIn('editor@example.test', 'correct-horse-battery-staple');

    expect(session.token()).toBe('token-one');
    expect(useSession.getState().status).toBe('signed-in');
  });

  it('refuses bad credentials without storing anything', async () => {
    mockFetch(() => json({ error: 'nope' }, 401));

    await expect(signIn('editor@example.test', 'wrong')).rejects.toThrow();
    expect(session.token()).toBeNull();
  });

  it('treats a login response with no token as a failure', async () => {
    mockFetch(() => json({ tokenType: 'Bearer' }));

    await expect(signIn('editor@example.test', 'x')).rejects.toThrow();
    expect(session.token()).toBeNull();
  });
});

describe('signOut', () => {
  it('clears the token in memory as well as calling the server', async () => {
    session.set('token-one');
    mockFetch(() => json({ ok: true }));

    await signOut();

    expect(session.token()).toBeNull();
    expect(calls.map((c) => c.url)).toContain('/api/logout');
  });
});

describe('restoreSession', () => {
  it('recovers a session from the httpOnly cookie on a fresh load', async () => {
    mockFetch(() => json({ accessToken: 'token-restored' }));

    await expect(restoreSession()).resolves.toBe(true);
    expect(session.token()).toBe('token-restored');
  });

  it('reports no session rather than throwing when there is no cookie', async () => {
    mockFetch(() => json({ error: 'no session' }, 401));

    await expect(restoreSession()).resolves.toBe(false);
    expect(useSession.getState().status).toBe('signed-out');
  });
});
