import type { AppReport, LoadedApp } from '@/shell/registry';

/**
 * Asks the service which apps it loaded.
 *
 * A plain `fetch`, not `apiFetch`, and with no token. The route is open on the Python service, and
 * on the Java engine it is not a route at all — Spring answers 401 for anything it does not know.
 * Sent through `apiFetch`, that 401 would trigger a refresh, then a retry, then a `NotSignedIn`,
 * and a perfectly good session would be sent to the login page because an engine has no app list.
 *
 * 401, 403 and 404 mean "this engine does not report its apps". Anything else that is not a 200 is
 * an engine that could not answer, and is thrown: showing every screen because the service is
 * down would be a guess presented as a fact.
 */
const HEALTH = '/api/engine/health';

const NOT_REPORTED = new Set([401, 403, 404]);

function isLoadedApp(value: unknown): value is LoadedApp {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return typeof candidate.name === 'string' && typeof candidate.version === 'string';
}

export async function readAppReport(): Promise<AppReport> {
  const response = await fetch(HEALTH, { cache: 'no-store' });
  if (NOT_REPORTED.has(response.status)) {
    return { kind: 'unreported' };
  }
  if (!response.ok) {
    throw new Error(`the engine could not say which apps it runs (GET /health: ${response.status})`);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { kind: 'unreported' };
  }
  const apps = (body as { apps?: unknown } | null)?.apps;
  if (!Array.isArray(apps)) {
    return { kind: 'unreported' };
  }
  return {
    kind: 'reported',
    apps: apps.filter(isLoadedApp).map(({ name, version }) => ({ name, version })),
  };
}
