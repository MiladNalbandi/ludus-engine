import type { NextConfig } from 'next';

/**
 * The engine's base URL is read on the server only.
 *
 * Not `NEXT_PUBLIC_`, deliberately. A public variable is inlined into the browser bundle, and the
 * browser never talks to the engine directly here — every call goes through this app's own route
 * handlers, so that the refresh token can live in an httpOnly cookie the page's JavaScript cannot
 * read. Exposing the engine URL to the client would invite someone to "simplify" that away.
 */
const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
