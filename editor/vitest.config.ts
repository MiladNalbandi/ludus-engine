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
  // Next.js requires `"jsx": "preserve"` in tsconfig, because Next compiles JSX itself. Vitest 3
  // compiled it anyway through esbuild; Vitest 5 runs on Vite 8, whose transformer honours
  // `preserve` and leaves the JSX in place, so a test importing a .tsx file fails to parse. The
  // tests are the only place this matters, so the transform is set here rather than in tsconfig.
  oxc: { jsx: { runtime: 'automatic' } },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['src/test/setup.ts'],
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
});
