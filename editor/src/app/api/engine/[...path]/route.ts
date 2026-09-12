import { NextResponse } from 'next/server';
import { engineBaseUrl } from '@/lib/engine';

/**
 * Forwards a request to the engine.
 *
 * The browser talks only to this origin, which buys two things. The refresh token can live in an
 * httpOnly cookie, because the only code that needs it runs here. And a self-hosted deployment can
 * leave the engine unpublished entirely — reachable on the compose network and nowhere else —
 * rather than exposing an API that needs its own CORS policy to be got right.
 *
 * The access token is not read or minted here. It arrives in the `Authorization` header the browser
 * sent, from a store that holds it in memory, and is passed through untouched. This handler is
 * deliberately not a place where a request becomes authenticated: if it minted tokens from the
 * cookie, every fetch from any page on this origin would be authenticated, including ones triggered
 * by a cross-site request.
 */
const FORWARDED_REQUEST_HEADERS = ['authorization', 'content-type', 'if-none-match', 'accept'];
const FORWARDED_RESPONSE_HEADERS = ['content-type', 'etag', 'cache-control', 'content-disposition'];

async function forward(request: Request, path: string[]): Promise<Response> {
  const url = new URL(request.url);
  const target = `${engineBaseUrl()}/${path.join('/')}${url.search}`;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) {
      headers.set(name, value);
    }
  }

  const engineResponse = await fetch(target, {
    method: request.method,
    headers,
    // GET and HEAD must not carry one, and duplex is required for a streamed body.
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
    // @ts-expect-error -- duplex is required by undici for a streaming body and is not yet in
    // the DOM RequestInit type. Without it, uploading an audio clip fails at runtime.
    duplex: 'half',
    redirect: 'manual',
    cache: 'no-store',
  });

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = engineResponse.headers.get(name);
    if (value) {
      responseHeaders.set(name, value);
    }
  }

  // The body is streamed rather than buffered, which matters for audio: the engine goes to some
  // trouble never to hold a clip in memory, and a proxy that read it whole would undo that here.
  return new Response(engineResponse.body, {
    status: engineResponse.status,
    headers: responseHeaders,
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context): Promise<Response> {
  return forward(request, (await context.params).path);
}

export async function POST(request: Request, context: Context): Promise<Response> {
  return forward(request, (await context.params).path);
}

export async function PUT(request: Request, context: Context): Promise<Response> {
  return forward(request, (await context.params).path);
}

export async function DELETE(request: Request, context: Context): Promise<Response> {
  return forward(request, (await context.params).path);
}

/** No other methods. An engine route added later is reachable only once it is named here. */
export async function OPTIONS(): Promise<NextResponse> {
  return NextResponse.json({ error: 'not supported' }, { status: 405 });
}
