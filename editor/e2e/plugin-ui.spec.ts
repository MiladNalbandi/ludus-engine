import { expect, test, type Page } from '@playwright/test';
import { spawn, execFileSync, type ChildProcess } from 'node:child_process';
import {
  appendFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

/**
 * The done-criterion of #76, walked end to end: installing a plugin with a `ui/` folder adds its
 * screen to the editor with no change to the editor, and removing the plugin removes the screen.
 *
 * It runs against the **Python** service — the Java engine has no plugins — and it runs that
 * service itself, because installing and removing a plugin means restarting it, as it does for a
 * plugin's backend: the service reads its plugins when it starts. The editor under test must be
 * pointed at the address this test serves on (`LUDUS_ENGINE_URL`).
 *
 * The plugin is `service/tests/fixtures/bulletin`, built with `wavemaker plugin build`, signed,
 * published to a registry made for this run and installed with `wavemaker plugin install` — the
 * path an author's plugin takes. Nothing in the editor names it.
 *
 * Needs, besides the editor stack's own variables:
 * - `LUDUS_E2E_SERVICE_PYTHON`: a Python with the service installed (`service/.venv/bin/python`);
 * - `WAVEMAKER_DATABASE_URL`, `WAVEMAKER_JWT_SECRET`: the service's database and signing key;
 *   the administrator is created from `LUDUS_E2E_EMAIL` and `LUDUS_E2E_PASSWORD`.
 * Without `LUDUS_E2E_SERVICE_PYTHON` the test is skipped, so the journey can run alone against
 * an engine this test cannot restart.
 */
const PYTHON = process.env.LUDUS_E2E_SERVICE_PYTHON;
const ENGINE_URL = new URL(process.env.LUDUS_ENGINE_URL ?? 'http://127.0.0.1:8000');
const EMAIL = process.env.LUDUS_E2E_EMAIL ?? 'ci@example.test';
const PASSWORD = process.env.LUDUS_E2E_PASSWORD ?? 'ci-not-a-real-password';
const FIXTURE = resolve(__dirname, '..', '..', 'service', 'tests', 'fixtures', 'bulletin');

test.describe('a plugin brings its own screen', () => {
  test.skip(!PYTHON, 'set LUDUS_E2E_SERVICE_PYTHON: this test runs the Python service itself');
  test.describe.configure({ mode: 'serial' });

  let work = '';
  let service: ChildProcess | null = null;

  const env = () => ({
    ...process.env,
    WAVEMAKER_PLUGINS_DIRECTORY: join(work, 'plugins'),
    WAVEMAKER_PLUGIN_REGISTRY: join(work, 'registry'),
    WAVEMAKER_TRUSTED_KEYS_DIRECTORY: join(work, 'trusted'),
    WAVEMAKER_ADMIN_EMAIL: EMAIL,
    WAVEMAKER_ADMIN_PASSWORD: PASSWORD,
  });

  const wavemaker = (...args: string[]) =>
    execFileSync(PYTHON ?? 'python', ['-m', 'wavemaker.platform.cli', 'plugin', ...args], {
      env: env(),
      encoding: 'utf8',
    });

  async function startService(): Promise<void> {
    service = spawn(
      PYTHON ?? 'python',
      [
        '-m',
        'uvicorn',
        '--factory',
        'wavemaker.platform.http.factory:create_app',
        '--host',
        ENGINE_URL.hostname,
        '--port',
        ENGINE_URL.port || '80',
      ],
      { env: env(), stdio: ['ignore', 'inherit', 'inherit'] },
    );
    const deadline = Date.now() + 60_000;
    while (Date.now() < deadline) {
      try {
        if ((await fetch(new URL('/health', ENGINE_URL))).ok) {
          return;
        }
      } catch {
        // Not listening yet.
      }
      await new Promise((settle) => setTimeout(settle, 250));
    }
    throw new Error(`the service did not answer /health at ${ENGINE_URL.href} within a minute`);
  }

  async function stopService(): Promise<void> {
    const running = service;
    service = null;
    if (!running || running.exitCode !== null) {
      return;
    }
    const exited = new Promise((settle) => running.once('exit', settle));
    running.kill('SIGTERM');
    await exited;
  }

  async function restartService(): Promise<void> {
    await stopService();
    await startService();
  }

  async function signIn(page: Page): Promise<void> {
    await page.goto('/login');
    await page.getByLabel('Email').fill(EMAIL);
    await page.getByLabel('Password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('heading', { name: 'Catalogue' })).toBeVisible();
  }

  const rail = (page: Page) => page.getByRole('navigation', { name: 'Apps' });
  const bundle = () => join(work, 'plugins', 'bulletin', 'ui', 'module.js');

  test.beforeAll(async () => {
    work = mkdtempSync(join(tmpdir(), 'ludus-plugin-ui-'));
    mkdirSync(join(work, 'plugins'));
    mkdirSync(join(work, 'trusted'));
    wavemaker('build', FIXTURE, '--out', join(work, 'built'));
    wavemaker('keygen', join(work, 'keys', 'publisher.pem'));
    writeFileSync(
      join(work, 'trusted', 'publisher.pub'),
      readFileSync(join(work, 'keys', 'publisher.pub')),
    );
    wavemaker(
      'publish',
      join(work, 'built', 'bulletin-1.0.0.wmp'),
      '--registry',
      join(work, 'registry'),
      '--key',
      join(work, 'keys', 'publisher.pem'),
    );
    await startService();
  });

  test.afterAll(async () => {
    await stopService();
    if (work) {
      rmSync(work, { recursive: true, force: true });
    }
  });

  test('without the plugin, the editor has no bulletin screen', async ({ page }) => {
    await signIn(page);

    await expect(rail(page).getByRole('link', { name: /Content/ })).toBeVisible();
    await expect(rail(page).getByRole('link', { name: /Bulletin/ })).toHaveCount(0);
    await page.goto('/bulletin');
    await expect(
      page.getByRole('heading', { name: 'Nothing lives at this address' }),
    ).toBeVisible();
  });

  test('installing it adds its screen, which talks to its own backend', async ({ page }) => {
    expect(wavemaker('install', 'bulletin@1.0.0')).toContain('installed bulletin@1.0.0');
    await restartService();

    const opened = await page.goto('/login');
    // The page that will run the plugin says where code may come from and go to.
    const policy = opened?.headers()['content-security-policy'] ?? '';
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toMatch(/script-src 'self'[^;]* blob:/);
    await signIn(page);

    const link = rail(page).getByRole('link', { name: /Bulletin/ });
    await expect(link).toBeVisible();
    await expect(link).toContainText('Installed plugin');
    await expect(link).toContainText('1.0.0');
    await link.click();

    await expect(page).toHaveURL(/\/bulletin$/);
    await expect(page.getByRole('heading', { name: 'Bulletin', level: 1 })).toBeVisible();
    // Fetched by the screen from GET /api/v1/bulletin/notice, which needs an editor's token.
    await expect(page.getByRole('heading', { name: 'Bulletin is installed' })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Pinned' }).getByRole('listitem')).toHaveCount(2);
    await expect(page.getByText('Screens that could not load')).toHaveCount(0);

    // Its styles reach its own screen and no other: `.screen-lede` is the shell's class.
    const lede = page.locator('[data-module="bulletin"] .screen-lede');
    await expect(lede).toHaveCSS('font-style', 'italic');
    await rail(page)
      .getByRole('link', { name: /Inventory/ })
      .click();
    await expect(page.locator('[data-module="inventory"] .screen-lede').first()).toHaveCSS(
      'font-style',
      'normal',
    );
  });

  test('a bundle changed after install is refused and never run', async ({ page }) => {
    const original = readFileSync(bundle());
    appendFileSync(bundle(), '\nglobalThis.__bulletinTampered = true;\n');
    try {
      // No restart: the service serves the disk, and reports the hash recorded at install.
      await signIn(page);

      const failed = page.getByRole('region', { name: 'Screens that could not load' });
      await expect(failed).toContainText('bulletin');
      await expect(failed).toContainText(
        'does not match the integrity recorded when it was installed, so it was not run',
      );
      await expect(rail(page).getByRole('link', { name: /Bulletin/ })).toHaveCount(0);
      expect(
        await page.evaluate(
          () => (globalThis as { __bulletinTampered?: boolean }).__bulletinTampered,
        ),
      ).toBeUndefined();
      // Every other screen is still there.
      await expect(rail(page).getByRole('link', { name: /Content/ })).toBeVisible();
    } finally {
      writeFileSync(bundle(), original);
    }
  });

  test('removing it removes the screen', async ({ page }) => {
    // R5 has no uninstall command: removing a plugin is removing its directory, and restarting.
    rmSync(join(work, 'plugins', 'bulletin'), { recursive: true, force: true });
    await restartService();

    await signIn(page);

    await expect(rail(page).getByRole('link', { name: /Bulletin/ })).toHaveCount(0);
    await expect(page.getByText('Screens that could not load')).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Running without a screen' })).not.toContainText(
      'bulletin',
    );
    await page.goto('/bulletin');
    await expect(
      page.getByRole('heading', { name: 'Nothing lives at this address' }),
    ).toBeVisible();
  });
});
