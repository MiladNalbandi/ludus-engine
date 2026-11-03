import { afterEach, describe, expect, it, vi } from 'vitest';
import { readAppReport } from '@/shell/health';
import { session, useSession } from '@/stores/session';

/**
 * Reading which apps the service loaded.
 *
 * `/health` is open on the Python service, deliberately: the app list is the only evidence from
 * outside that the loader ran. It is read without the access token, so a stale token cannot turn
 * "which screens exist" into a refresh and a redirect to the login page.
 */
type Call = { url: string; authorization: string | null };
let calls: Call[] = [];

function respond(status: number, body?: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      calls.push({
        url: typeof input === 'string' ? input : input.toString(),
        authorization: new Headers(init?.headers).get('Authorization'),
      });
      return new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
}

afterEach(() => {
  calls = [];
  useSession.setState({ accessToken: null, status: 'unknown' });
});

describe('readAppReport', () => {
  it('returns the apps the service reports, with their versions', async () => {
    respond(200, {
      status: 'ok',
      version: '0.4.0',
      apps: [
        { name: 'content', version: '1.0.0' },
        { name: 'economy', version: '1.2.0' },
      ],
    });

    await expect(readAppReport()).resolves.toEqual({
      kind: 'reported',
      apps: [
        { name: 'content', version: '1.0.0' },
        { name: 'economy', version: '1.2.0' },
      ],
    });
  });

  it('asks the engine through the proxy, and never sends the access token', async () => {
    session.set('a-token');
    respond(200, { status: 'ok', apps: [] });

    await readAppReport();

    expect(calls).toEqual([{ url: '/api/engine/health', authorization: null }]);
  });

  it('treats an engine with no app list as one that does not report its apps', async () => {
    for (const status of [401, 403, 404]) {
      respond(status, { error: 'nope' });
      await expect(readAppReport()).resolves.toEqual({ kind: 'unreported' });
    }
  });

  it('treats a 200 without an app list the same way', async () => {
    respond(200, { status: 'UP' });

    await expect(readAppReport()).resolves.toEqual({ kind: 'unreported' });
  });

  it('skips entries that are not apps rather than inventing a screen for them', async () => {
    respond(200, {
      apps: [{ name: 'content', version: '1.0.0' }, { version: '1' }, 'media', null],
    });

    await expect(readAppReport()).resolves.toEqual({
      kind: 'reported',
      apps: [{ name: 'content', version: '1.0.0' }],
    });
  });

  it("passes on an installed plugin's ui entry as sent, for the plugin loader to judge", async () => {
    const ui = { entry: '/plugins/bulletin/1.0.0/ui/module.js', api: 2, integrity: 'sha384-x' };
    respond(200, {
      apps: [
        { name: 'bulletin', version: '1.0.0', ui },
        { name: 'quests', version: '2.0.0', ui: 'not an object' },
        { name: 'content', version: '1.0.0', extra: 'dropped' },
      ],
    });

    await expect(readAppReport()).resolves.toEqual({
      kind: 'reported',
      apps: [
        { name: 'bulletin', version: '1.0.0', ui },
        // Malformed, and still listed: the loader reports it against the plugin.
        { name: 'quests', version: '2.0.0', ui: 'not an object' },
        { name: 'content', version: '1.0.0' },
      ],
    });
  });

  it('fails loudly when the engine cannot answer, instead of showing every screen', async () => {
    respond(502);

    await expect(readAppReport()).rejects.toThrow(/502/);
  });
});
