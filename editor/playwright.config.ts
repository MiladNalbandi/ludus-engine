import { defineConfig, devices } from '@playwright/test';

/**
 * The end-to-end run, against a stack that is already up.
 *
 * No `webServer` block: this runs against `docker compose up` in CI, which is the only place the
 * real engine, a real PostgreSQL, a real volume and the editor container all exist together. A
 * Playwright-managed dev server would test the editor against nothing, which is the half already
 * covered by the unit tests.
 */
const baseURL = process.env.LUDUS_EDITOR_URL ?? 'http://localhost:3000';

export default defineConfig({
  testDir: './e2e',
  // One worker. The journey signs in, edits and publishes against one project's catalogue, so two
  // copies of it running at once would fight over the same waves.
  workers: 1,
  // Retries only in CI, and only because a container that has just started can be slow to answer
  // its first request -- not to paper over a flaky assertion.
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
