import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

/**
 * No React plugin here, deliberately.
 *
 * These tests cover the stores and the fetch wrapper, which are plain TypeScript. Adding
 * `@vitejs/plugin-react` pulls in a second, different Vite from the one Vitest bundles, and the two
 * disagree about their plugin types well enough to fail `tsc --noEmit` while every test still
 * passes. It goes back in when there is a component test that needs it, pinned against whatever
 * Vite Vitest ships at that point.
 */
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['src/test/setup.ts'],
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
});
