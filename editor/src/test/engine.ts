import { vi } from 'vitest';
import { session } from '@/stores/session';

/**
 * A stand-in engine for the module data layers' tests.
 *
 * Each test answers by method and path, and gets back every request exactly as `fetch` received
 * it, so a test can assert on the path, the query, the method and the body a data layer sent —
 * which is the part that has to match the frozen contract.
 */
export type SentRequest = {
  method: string;
  /** The engine path, without the editor's `/api/engine` proxy prefix. */
  path: string;
  query: URLSearchParams;
  contentType: string | null;
  authorization: string | null;
  /** The body decoded as JSON when it is a JSON string, otherwise as sent (a FormData, say). */
  body: unknown;
  /** The body exactly as sent, when it was a string. */
  raw: string | null;
};

type Answer = Response | ((request: SentRequest) => Response);

const PROXY = '/api/engine';

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export function empty(status = 204): Response {
  return new Response(null, { status });
}

export function mockEngine(answers: Record<string, Answer>): SentRequest[] {
  const sent: SentRequest[] = [];
  session.set('test-token');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = new URL(typeof input === 'string' ? input : input.toString(), 'http://editor');
      const headers = new Headers(init?.headers);
      const raw = init?.body;
      let body: unknown = raw ?? null;
      if (typeof raw === 'string') {
        try {
          body = JSON.parse(raw);
        } catch {
          body = raw;
        }
      }
      const request: SentRequest = {
        method: init?.method ?? 'GET',
        path: url.pathname.startsWith(PROXY) ? url.pathname.slice(PROXY.length) : url.pathname,
        query: url.searchParams,
        contentType: headers.get('Content-Type'),
        authorization: headers.get('Authorization'),
        body,
        raw: typeof raw === 'string' ? raw : null,
      };
      sent.push(request);
      const answer = answers[`${request.method} ${request.path}`];
      if (!answer) {
        return json({ detail: `no answer for ${request.method} ${request.path}` }, 599);
      }
      return typeof answer === 'function' ? answer(request) : answer.clone();
    }),
  );
  return sent;
}
