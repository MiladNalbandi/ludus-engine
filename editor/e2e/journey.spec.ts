import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/**
 * The acceptance criterion from #9, walked end to end: log in, build, preview, save, publish, and
 * fetch the result from the public API.
 *
 * This is the only test in the repository that exercises the whole system at once — the editor
 * container, the engine, PostgreSQL and the audio volume — so it is deliberately about the *seam*
 * between them rather than about any one part. Everything that can be checked without a stack
 * already is: the conversion, the stores, the simulator and the fetch wrapper have unit tests, and
 * the engine has 343 of its own.
 *
 * What only this can catch is the shape of failure where every component works and the system does
 * not: a proxy that drops a header, a cookie the browser will not send back, a published wave the
 * public route cannot see.
 */
const ENGINE_URL = process.env.LUDUS_ENGINE_URL ?? 'http://localhost:8080';
const EMAIL = process.env.LUDUS_E2E_EMAIL ?? 'ci@example.test';
const PASSWORD = process.env.LUDUS_E2E_PASSWORD ?? 'ci-not-a-real-password';

/** A wave id unique to this run, so a retry never collides with its own earlier attempt. */
const WAVE_ID = `e2e_${Date.now().toString(36)}`;

/** Well clear of the demo waves and the bulk tests, which take low orders. */
const WAVE_ORDER = 9000 + (Date.now() % 500);

/** Named `waveDocument`, not `document`: inside `page.evaluate` the DOM global is needed. */
function waveDocument(id: string, order: number): string {
  return JSON.stringify({
    id,
    schema_version: 1,
    version: '1.0.0',
    name: 'End to end',
    category: 'easy',
    duration: 10,
    constraints: { time_limit: 10, max_lights: 1, max_bullets_on_screen: 10 },
    progression_config: {
      order,
      cube_scoring: { enemy_destroyed: 5, enemy_out_of_view: 1, bonus_collected: 10 },
    },
    spawn_rules: [
      {
        entity_type: 'light',
        count: 1,
        spawn_delay: 0,
        spawn_position: { type: 'screen_relative', screen_x: 0.5, screen_y: 0.2 },
        movement_rules: {
          sequence: [{ type: 'patrol', duration: 4, patrol_config: { speed: 40, direction: 'horizontal' } }],
        },
      },
    ],
  });
}

/** Seeds the wave through the engine's own API, so the UI journey has something to open. */
async function seedWave(request: APIRequestContext): Promise<void> {
  const token = await request.post(`${ENGINE_URL}/api/v1/auth/token`, {
    data: { email: EMAIL, password: PASSWORD },
  });
  expect(token.ok(), 'the engine accepted the CI administrator').toBeTruthy();
  const { accessToken } = (await token.json()) as { accessToken: string };

  const created = await request.post(`${ENGINE_URL}/api/v1/admin/waves`, {
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    data: waveDocument(WAVE_ID, WAVE_ORDER),
  });
  expect(created.status(), await created.text()).toBe(201);
}

async function signIn(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(EMAIL);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Catalogue' })).toBeVisible();
}

test.describe('the editor, against a real stack', () => {
  test.beforeAll(async ({ playwright }) => {
    const request = await playwright.request.newContext();
    try {
      await seedWave(request);
    } finally {
      await request.dispose();
    }
  });

  test('log in, build, preview, save, publish, and fetch it publicly', async ({ page, request }) => {
    await signIn(page);

    // --- the refresh token must not be readable by page JavaScript -------------
    const cookies = await page.context().cookies();
    const refresh = cookies.find((cookie) => cookie.name === 'ludus_refresh');
    expect(refresh, 'a refresh cookie was set').toBeTruthy();
    expect(refresh!.httpOnly, 'the refresh cookie is httpOnly').toBe(true);
    expect(refresh!.sameSite).toBe('Lax');

    // The whole reason the access token lives in memory. If this ever finds one, an XSS hole
    // becomes a stolen session that outlives the tab.
    const stored = await page.evaluate(() => ({
      local: JSON.stringify(window.localStorage),
      session: JSON.stringify(window.sessionStorage),
      readableCookies: document.cookie,
    }));
    expect(stored.local).not.toContain('ey');
    expect(stored.session).not.toContain('ey');
    expect(stored.readableCookies).not.toContain('ludus_refresh');

    // --- open the wave --------------------------------------------------------
    await page.getByRole('link', { name: WAVE_ID }).click();
    await expect(page.getByRole('heading', { name: 'End to end' })).toBeVisible();

    // --- build: add a movement ------------------------------------------------
    await expect(page.getByRole('button', { name: 'patrol, 4 seconds' })).toBeVisible();
    await page.getByRole('button', { name: '+ wait' }).click();

    // --- preview: the canvas draws, and the scrubber moves the playhead -------
    await expect(page.getByLabel('wave preview')).toBeVisible();
    await page.getByLabel('playhead').fill('2');
    await expect(page.getByText(/playhead at 2\.00s/)).toBeVisible();

    // --- save -----------------------------------------------------------------
    await page.getByRole('button', { name: 'Save draft' }).click();
    await expect(page.getByText('unsaved changes')).toBeHidden();

    // The added movement survived the round trip through the engine.
    await page.reload();
    await expect(page.getByRole('button', { name: /^wait, \d/ })).toBeVisible();

    // --- publish, from the catalogue ------------------------------------------
    await page.getByRole('link', { name: 'Catalogue' }).click();
    const row = page.getByRole('listitem').filter({ hasText: WAVE_ID });
    await row.getByRole('button', { name: 'Publish' }).click();
    await expect(row.getByText('published')).toBeVisible();

    // --- and a game client can fetch it, with no credential -------------------
    const served = await request.get(`${ENGINE_URL}/api/v1/public/waves/${WAVE_ID}/raw`);
    expect(served.status(), 'the published wave is served publicly').toBe(200);

    const body = (await served.json()) as { spawn_rules: { movement_rules: { sequence: unknown[] } }[] };
    expect(
      body.spawn_rules[0]!.movement_rules.sequence,
      'the movement added in the browser reached the public API',
    ).toHaveLength(2);

    // The ETag the client would cache against, and the 304 it would get back.
    const etag = served.headers()['etag'];
    expect(etag).toBeTruthy();
    const revalidated = await request.get(`${ENGINE_URL}/api/v1/public/waves/${WAVE_ID}/raw`, {
      headers: { 'If-None-Match': etag! },
    });
    expect(revalidated.status()).toBe(304);
  });

  test('a draft is invisible to a client while its editor can see it', async ({ page, request }) => {
    const draftId = `${WAVE_ID}_draft`;
    const context = await page.context().request;
    const token = await context.post(`${ENGINE_URL}/api/v1/auth/token`, {
      data: { email: EMAIL, password: PASSWORD },
    });
    const { accessToken } = (await token.json()) as { accessToken: string };
    await context.post(`${ENGINE_URL}/api/v1/admin/waves`, {
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      data: waveDocument(draftId, WAVE_ORDER + 1),
    });

    await signIn(page);
    await expect(page.getByRole('link', { name: draftId })).toBeVisible();

    // 404, never 403. A client that can tell "hidden" from "absent" has been told about unreleased
    // content, which is the one thing publication exists to control.
    const served = await request.get(`${ENGINE_URL}/api/v1/public/waves/${draftId}/raw`);
    expect(served.status()).toBe(404);
  });

  test('signing out ends the session', async ({ page }) => {
    await signIn(page);
    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();

    // The cookie is gone, so the middleware sends a fresh visit to the login page rather than to a
    // catalogue that will fail to load.
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  });
});
