import { apiFetch } from '@/lib/api';

/**
 * The way module screens talk to the engine: `apiFetch`, with a refusal turned into an error that
 * carries what the engine said.
 *
 * The engine's message is the useful part of a refusal. A validation failure names the JSON Pointer
 * of the field that is wrong, and a screen that said only "422" would leave an author guessing which
 * field to open. Both services are understood: the Python one answers `{"detail": ...}`, with a
 * list of errors for a body FastAPI itself rejected, and the Java one a problem document.
 */
export class Refused extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'Refused';
  }
}

type ValidationError = { loc?: unknown[]; msg?: unknown };

function describeDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry: ValidationError) => {
        if (typeof entry?.msg !== 'string') {
          return null;
        }
        const where = Array.isArray(entry.loc) ? entry.loc.map(String).join('.') : '';
        return where ? `${where}: ${entry.msg}` : entry.msg;
      })
      .filter((part): part is string => part !== null);
    return parts.length > 0 ? parts.join('; ') : null;
  }
  return null;
}

async function messageOf(response: Response, fallback: string): Promise<string> {
  const text = await response.text().catch(() => '');
  if (!text.trim()) {
    return fallback;
  }
  try {
    const body = JSON.parse(text) as Record<string, unknown>;
    return (
      describeDetail(body.detail) ??
      describeDetail(body.message) ??
      describeDetail(body.title) ??
      describeDetail(body.error) ??
      fallback
    );
  } catch {
    // Not JSON: a proxy's error page or a plain sentence. Long pages are cut, not shown whole.
    return text.length > 300 ? `${text.slice(0, 300)}…` : text;
  }
}

/** Calls an engine path and resolves with the response if it is a 2xx. */
export async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    const fallback = `${init.method ?? 'GET'} ${path} failed: ${response.status}`;
    throw new Refused(response.status, await messageOf(response, fallback));
  }
  return response;
}

export async function sendJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

/** The body as text, untouched, for documents the engine stores byte for byte. */
export async function sendText(path: string, init: RequestInit = {}): Promise<string> {
  return (await send(path, init)).text();
}

/** A JSON request body. */
export function jsonBody(method: string, value: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  };
}

/** One path segment, encoded. */
export const segment = (value: string): string => encodeURIComponent(value);
