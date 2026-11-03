import type { NextConfig } from 'next';

/**
 * The engine's base URL is read on the server only.
 *
 * Not `NEXT_PUBLIC_`, deliberately. A public variable is inlined into the browser bundle, and the
 * browser never talks to the engine directly here — every call goes through this app's own route
 * handlers, so that the refresh token can live in an httpOnly cookie the page's JavaScript cannot
 * read. Exposing the engine URL to the client would invite someone to "simplify" that away.
 */
const development = process.env.NODE_ENV !== 'production';

/**
 * The editor's Content-Security-Policy. Since R8 an installed plugin's screen runs on this page,
 * with the signed-in author's token in reach, so the page says where code may come from and where
 * it may send things:
 *
 * - scripts only from this origin, or from a `blob:` URL — which is how the shell evaluates a
 *   plugin bundle whose bytes it has just checked. Inline scripts stay allowed because Next.js
 *   writes its own; every other origin is refused, so a plugin cannot pull in code from elsewhere;
 * - `connect-src 'self'`: a request may go to this origin only — which proxies to the engine — so
 *   a script cannot `fetch` the token to another host;
 * - no plugins, no framing, forms only to this origin.
 *
 * Development adds what `next dev` needs: `eval` for its source maps, and a socket for reloads.
 * The engine proxy is left out, so a plugin file passed through it keeps the service's own
 * policy (`default-src 'none'; sandbox`) rather than gaining this one.
 */
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' blob:${development ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "font-src 'self' data:",
  `connect-src 'self'${development ? ' ws: wss:' : ''}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/((?!api/engine/).*)',
        headers: [
          { key: 'Content-Security-Policy', value: contentSecurityPolicy },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
        ],
      },
    ];
  },
  // The wave editor moved inside the content module. An address someone bookmarked before the
  // shell existed still opens the same wave.
  async redirects() {
    return [{ source: '/waves/:id', destination: '/content/waves/:id', permanent: false }];
  },
};

export default nextConfig;
