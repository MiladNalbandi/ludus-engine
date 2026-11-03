import { describe, expect, it, vi } from 'vitest';
import { createHash, webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { act, createElement, type ComponentType } from 'react';
import { createRoot } from 'react-dom/client';
import { session } from '@/stores/session';
import { builtInModules } from '@/modules';
import type { EditorModule, ModuleHost, ModuleScreenProps } from '@/shell/module';
import { moduleHost } from '@/shell/host';
import { matchesIntegrity } from '@/shell/integrity';
import { loadShellModules, type LoaderDeps } from '@/shell/plugins';
import type { AppReport, LoadedApp } from '@/shell/registry';

/**
 * The second half of #76, at the shell: an installed plugin's screen joins the editor from the
 * `/health` report alone, through the same registry checks as a built-in, and a plugin that is
 * wrong in any way is reported beside its app while everything else carries on.
 *
 * The fetch, the digest and the evaluation are injected, so each step can be made to fail on its
 * own. One test evaluates the real fixture bundle, `service/tests/fixtures/bulletin/ui/module.js`,
 * the file the service tests install and serve.
 */
const FIXTURE = resolve(
  __dirname,
  '..',
  '..',
  '..',
  'service',
  'tests',
  'fixtures',
  'bulletin',
  'ui',
  'module.js',
);

const Screen: ComponentType<ModuleScreenProps> = () => null;

function sri(data: ArrayBuffer | Uint8Array): string {
  return `sha384-${createHash('sha384').update(new Uint8Array(data)).digest('base64')}`;
}

const nodeDigest = (algorithm: string, data: ArrayBuffer) =>
  webcrypto.subtle.digest(algorithm, data);

type Bundle = { bytes: Uint8Array; namespace: unknown };

/** A bundle: some bytes, and what evaluating them yields. */
function bundle(namespace: unknown, text = `// ${Math.random()}`): Bundle {
  return { bytes: new TextEncoder().encode(text), namespace };
}

function factoryFor(module: Partial<EditorModule>) {
  return {
    default: () => ({
      api: 2,
      label: module.app,
      summary: `the ${module.app} screen`,
      routes: [{ path: '', title: 'Home', screen: Screen }],
      ...module,
    }),
  };
}

function plugin(name: string, extra: Partial<LoadedApp> = {}): LoadedApp {
  return {
    name,
    version: '1.0.0',
    ui: { entry: `/plugins/${name}/1.0.0/ui/module.js`, api: 2, integrity: 'unset' },
    ...extra,
  };
}

function report(...apps: (LoadedApp | string)[]): AppReport {
  return {
    kind: 'reported',
    apps: apps.map((app) => (typeof app === 'string' ? { name: app, version: '1.0.0' } : app)),
  };
}

/**
 * Loader dependencies serving `bundles` by URL. Each app's integrity in the report is set to its
 * bundle's real hash unless the test says otherwise, so a mismatch is always deliberate.
 */
function harness(bundles: Record<string, Bundle>) {
  const fetched: string[] = [];
  const evaluated: string[] = [];
  const scoped: { slug: string; css: string }[] = [];
  const deps: LoaderDeps = {
    host: moduleHost,
    fetchBundle: vi.fn(async (url: string) => {
      fetched.push(url);
      const found = bundles[url];
      return found
        ? new Response(found.bytes as Uint8Array<ArrayBuffer>, {
            headers: { 'Content-Type': 'text/javascript; charset=utf-8' },
          })
        : new Response('missing', { status: 404 });
    }),
    matches: (data, integrity) => matchesIntegrity(data, integrity, nodeDigest),
    evaluate: vi.fn(async (data: ArrayBuffer) => {
      const text = new TextDecoder().decode(data);
      const found = Object.entries(bundles).find(
        ([, b]) => new TextDecoder().decode(b.bytes) === text,
      );
      evaluated.push(found?.[0] ?? '?');
      const namespace = found?.[1].namespace;
      if (namespace instanceof Error) {
        throw namespace;
      }
      return namespace;
    }),
    scopeStyles: vi.fn((slug: string, css: string) => {
      scoped.push({ slug, css });
      return { slug } as unknown as CSSStyleSheet;
    }),
  };
  /** The app as /health would list it, carrying the true integrity of its bundle. */
  const listed = (name: string, extra: Partial<LoadedApp> = {}): LoadedApp => {
    const entry = `/plugins/${name}/1.0.0/ui/module.js`;
    const found = bundles[`/api/engine${entry}`];
    return plugin(name, {
      ui: { entry, api: 2, integrity: found ? sri(found.bytes) : 'sha384-AAAA' },
      ...extra,
    });
  };
  return { deps, fetched, evaluated, scoped, listed };
}

const at = (name: string) => `/api/engine/plugins/${name}/1.0.0/ui/module.js`;

describe('an installed plugin brings its screen', () => {
  it('adds the screen from the report alone, beside the built-in modules', async () => {
    const { deps, listed } = harness({
      [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'bulletin' })),
    });

    const shell = await loadShellModules(
      report('content', listed('bulletin')),
      builtInModules,
      deps,
    );

    expect(shell.failures).toEqual([]);
    const visible = shell.registry.visible(report('content', listed('bulletin')));
    expect(visible.map((entry) => entry.module.app)).toEqual(['content', 'bulletin']);
    expect(shell.installed).toEqual(new Set(['bulletin']));
    const found = shell.registry.resolve(report('content', listed('bulletin')), 'bulletin', []);
    expect(found.kind).toBe('screen');
  });

  it('removes the screen when a later report no longer lists the plugin', async () => {
    const { deps, listed } = harness({
      [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'bulletin' })),
    });
    await loadShellModules(report('content', listed('bulletin')), builtInModules, deps);

    const after = await loadShellModules(report('content'), builtInModules, deps);

    expect(after.registry.all().map((module) => module.app)).not.toContain('bulletin');
    expect(after.registry.resolve(report('content'), 'bulletin', [])).toEqual({ kind: 'unknown' });
  });

  it('fetches the bundle through the editor proxy, and evaluates the bytes it checked', async () => {
    const { deps, fetched, evaluated, listed } = harness({
      [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'bulletin' })),
    });

    await loadShellModules(report(listed('bulletin')), builtInModules, deps);

    expect(fetched).toEqual(['/api/engine/plugins/bulletin/1.0.0/ui/module.js']);
    expect(evaluated).toEqual([at('bulletin')]);
  });

  it('hands the factory the shell host, so the plugin renders with the shell React', async () => {
    let given: ModuleHost | null = null;
    const { deps, listed } = harness({
      [at('bulletin')]: bundle({
        default: (host: ModuleHost) => {
          given = host;
          return factoryFor({ app: 'bulletin', slug: 'bulletin' }).default();
        },
      }),
    });

    await loadShellModules(report(listed('bulletin')), builtInModules, deps);

    expect(given).toBe(moduleHost);
    expect(Object.isFrozen(moduleHost) && Object.isFrozen(moduleHost.engine)).toBe(true);
  });

  it('scopes the module styles to its own slug', async () => {
    const { deps, scoped, listed } = harness({
      [at('bulletin')]: bundle(
        factoryFor({ app: 'bulletin', slug: 'notices', styles: '.panel { color: red }' }),
      ),
    });

    const shell = await loadShellModules(report(listed('bulletin')), builtInModules, deps);

    expect(scoped).toEqual([{ slug: 'notices', css: '.panel { color: red }' }]);
    expect(shell.sheets).toHaveLength(1);
  });

  it('loads the real fixture bundle and renders it with the shell React', async () => {
    const bytes = readFileSync(FIXTURE);
    // The same bytes, evaluated as an ES module from a URL that carries them — as the browser
    // does with a blob: URL, which Node cannot import.
    const namespace = (await import(
      /* @vite-ignore */ `data:text/javascript;base64,${bytes.toString('base64')}`
    )) as unknown;
    const { deps } = harness({ [at('bulletin')]: { bytes: new Uint8Array(bytes), namespace } });
    const entry = '/plugins/bulletin/1.0.0/ui/module.js';
    const listed = report(plugin('bulletin', { ui: { entry, api: 2, integrity: sri(bytes) } }));

    const shell = await loadShellModules(listed, builtInModules, deps);

    expect(shell.failures).toEqual([]);
    const found = shell.registry.resolve(listed, 'bulletin', []);
    expect(found.kind === 'screen' && found.module.label).toBe('Bulletin');
    expect(found.kind === 'screen' && found.module.styles).toContain('.screen-lede');

    // Its screen calls its own backend through the shell's helpers, as the signed-in author.
    session.set('author-token');
    const calls: { url: string; authorization: string | null }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        calls.push({
          url: String(input),
          authorization: new Headers(init?.headers).get('Authorization'),
        });
        return Response.json({
          title: 'Pinned',
          body: 'Hello from the plugin',
          pinned: ['one', 'two'],
        });
      }),
    );
    const container = document.createElement('div');
    document.body.append(container);
    const root = createRoot(container);
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    if (found.kind !== 'screen') {
      throw new Error('no screen');
    }
    await act(async () => {
      root.render(createElement(found.route.screen, { params: {}, href: () => '/bulletin' }));
    });

    expect(calls).toEqual([
      { url: '/api/engine/api/v1/bulletin/notice', authorization: 'Bearer author-token' },
    ]);
    expect(container.querySelector('h1')?.textContent).toBe('Bulletin');
    expect(container.querySelector('h2')?.textContent).toBe('Pinned');
    expect([...container.querySelectorAll('li')].map((li) => li.textContent)).toEqual([
      'one',
      'two',
    ]);
    act(() => root.unmount());
    container.remove();
    session.clear();
  });
});

describe('a plugin that is wrong is reported, and nothing else is affected', () => {
  async function failureFor(
    bundles: Record<string, Bundle>,
    app: (h: ReturnType<typeof harness>) => LoadedApp,
  ) {
    const h = harness(bundles);
    const shell = await loadShellModules(report('content', app(h)), builtInModules, h.deps);
    // Whatever went wrong, the built-in modules are all still there.
    expect(shell.registry.all().slice(0, builtInModules.length)).toEqual([...builtInModules]);
    return { shell, ...h };
  }

  it('refuses a bundle whose bytes do not match the integrity, and never evaluates it', async () => {
    const tampered = bundle(factoryFor({ app: 'bulletin', slug: 'bulletin' }), '// tampered');
    const { shell, evaluated } = await failureFor({ [at('bulletin')]: tampered }, () =>
      plugin('bulletin', {
        ui: {
          entry: '/plugins/bulletin/1.0.0/ui/module.js',
          api: 2,
          integrity: sri(new TextEncoder().encode('// original')),
        },
      }),
    );

    expect(evaluated).toEqual([]);
    expect(shell.failures).toEqual([
      {
        app: 'bulletin',
        version: '1.0.0',
        reason:
          'its bundle does not match the integrity recorded when it was installed, so it was not run',
      },
    ]);
    expect(shell.registry.all().map((module) => module.app)).not.toContain('bulletin');
  });

  it('refuses an integrity it cannot read rather than skipping the check', async () => {
    const { shell, evaluated } = await failureFor(
      { [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'bulletin' })) },
      () =>
        plugin('bulletin', {
          ui: { entry: '/plugins/bulletin/1.0.0/ui/module.js', api: 2, integrity: 'md5-abc' },
        }),
    );

    expect(evaluated).toEqual([]);
    expect(shell.failures[0]?.reason).toMatch(/integrity this editor cannot read/);
  });

  it('reports a bundle the service could not serve', async () => {
    const { shell } = await failureFor({}, (h) => h.listed('bulletin'));

    expect(shell.failures[0]?.reason).toBe(
      'its bundle could not be fetched (GET /plugins/bulletin/1.0.0/ui/module.js: 404)',
    );
  });

  it('reports a bundle that throws while it is evaluated', async () => {
    const { shell } = await failureFor(
      { [at('bulletin')]: bundle(new SyntaxError('Unexpected token')) },
      (h) => h.listed('bulletin'),
    );

    expect(shell.failures[0]?.reason).toBe('its bundle failed while loading: Unexpected token');
  });

  it('reports a bundle whose default export is not a factory', async () => {
    const { shell } = await failureFor(
      { [at('bulletin')]: bundle({ default: { api: 1, app: 'bulletin', slug: 'bulletin' } }) },
      (h) => h.listed('bulletin'),
    );

    expect(shell.failures[0]?.reason).toMatch(/default export is not a module factory/);
  });

  it('reports a factory that throws', async () => {
    const { shell } = await failureFor(
      {
        [at('bulletin')]: bundle({
          default: () => {
            throw new Error('no host, no screen');
          },
        }),
      },
      (h) => h.listed('bulletin'),
    );

    expect(shell.failures[0]?.reason).toBe('its module factory threw: no host, no screen');
  });

  it('refuses a module that claims to be the screen for another app', async () => {
    const { shell } = await failureFor(
      { [at('bulletin')]: bundle(factoryFor({ app: 'economy', slug: 'bulletin' })) },
      (h) => h.listed('bulletin'),
    );

    expect(shell.failures[0]?.reason).toBe(
      "its module says it is the screen for 'economy', but it was installed as 'bulletin'",
    );
  });

  it('refuses a bundle written for interface version 1, which would need its own React', async () => {
    const { shell } = await failureFor(
      { [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'bulletin', api: 1 })) },
      (h) => h.listed('bulletin'),
    );

    expect(shell.failures[0]?.reason).toMatch(/interface version 1, not 2/);
  });

  it('refuses an interface version it does not implement without fetching anything', async () => {
    const { shell, fetched } = await failureFor({}, () =>
      plugin('bulletin', {
        ui: { entry: '/plugins/bulletin/1.0.0/ui/module.js', api: 3, integrity: 'sha384-AAAA' },
      }),
    );

    expect(fetched).toEqual([]);
    expect(shell.failures[0]?.reason).toMatch(/version 3/);
  });

  it('refuses an entry that is not the plugin own UI address, without fetching it', async () => {
    for (const entry of [
      '/api/v1/admin/items',
      '/plugins/other/1.0.0/ui/module.js',
      '/plugins/bulletin/2.0.0/ui/module.js',
      '/plugins/bulletin/1.0.0/ui/../../../api/v1/me',
      '/plugins/bulletin/1.0.0/ui/%2e%2e/x.js',
      'https://elsewhere.example/plugins/bulletin/1.0.0/ui/module.js',
    ]) {
      const { shell, fetched } = await failureFor({}, () =>
        plugin('bulletin', { ui: { entry, api: 2, integrity: 'sha384-AAAA' } }),
      );
      expect(fetched, entry).toEqual([]);
      expect(shell.failures[0]?.reason, entry).toMatch(/not its own plugin UI route/);
    }
  });

  it('reports a ui entry it cannot read', async () => {
    const { shell } = await failureFor({}, () => plugin('bulletin', { ui: 'module.js' }));

    expect(shell.failures[0]?.reason).toMatch(/form this editor does not read/);
  });

  it('keeps the built-in module when a plugin takes its slug', async () => {
    const { shell } = await failureFor(
      { [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'content' })) },
      (h) => h.listed('bulletin'),
    );

    expect(shell.failures[0]?.reason).toBe(
      "the shell refused it: two modules are mounted at slug 'content'",
    );
    const found = shell.registry.resolve(report('content'), 'content', []);
    expect(found.kind === 'screen' && found.module.app).toBe('content');
  });

  it('runs a plugin module through the same checks as a built-in one', async () => {
    const { shell } = await failureFor(
      { [at('bulletin')]: bundle(factoryFor({ app: 'bulletin', slug: 'login' })) },
      (h) => h.listed('bulletin'),
    );
    expect(shell.failures[0]?.reason).toBe(
      "the shell refused it: module slug 'login' is reserved by the shell",
    );

    const malformed = await failureFor(
      {
        [at('bulletin')]: bundle({
          default: () => ({ api: 2, app: 'bulletin', slug: 'bulletin', label: 'B', summary: '' }),
        }),
      },
      (h) => h.listed('bulletin'),
    );
    expect(malformed.shell.failures[0]?.reason).toBe(
      "the shell refused it: module 'bulletin' has no list of routes",
    );
  });

  it('keeps the first of two plugins at one slug, in the order the service listed them', async () => {
    const h = harness({
      [at('alpha')]: bundle(factoryFor({ app: 'alpha', slug: 'notes' })),
      [at('beta')]: bundle(factoryFor({ app: 'beta', slug: 'notes' })),
    });

    const shell = await loadShellModules(
      report(h.listed('alpha'), h.listed('beta')),
      builtInModules,
      h.deps,
    );

    expect(shell.installed).toEqual(new Set(['alpha']));
    expect(shell.failures.map((failure) => failure.app)).toEqual(['beta']);
  });

  it('reports styles that cannot be scoped, and leaves the screen out', async () => {
    const h = harness({
      [at('bulletin')]: bundle(
        factoryFor({ app: 'bulletin', slug: 'bulletin', styles: '@font-face {}' }),
      ),
    });
    h.deps.scopeStyles = () => {
      throw new Error('its styles use @font-face, which cannot be scoped to one module');
    };

    const shell = await loadShellModules(report(h.listed('bulletin')), builtInModules, h.deps);

    expect(shell.failures[0]?.reason).toBe(
      'its styles use @font-face, which cannot be scoped to one module',
    );
    expect(shell.installed.size).toBe(0);
  });

  it('loads the good plugin when another one fails', async () => {
    const h = harness({
      [at('alpha')]: bundle(new Error('broken')),
      [at('beta')]: bundle(factoryFor({ app: 'beta', slug: 'beta' })),
    });

    const shell = await loadShellModules(
      report(h.listed('alpha'), h.listed('beta')),
      builtInModules,
      h.deps,
    );

    expect(shell.failures.map((failure) => failure.app)).toEqual(['alpha']);
    expect(shell.installed).toEqual(new Set(['beta']));
  });
});

describe('what the loader leaves alone', () => {
  it('loads nothing from an engine that does not report its apps', async () => {
    const h = harness({});

    const shell = await loadShellModules({ kind: 'unreported' }, builtInModules, h.deps);

    expect(h.fetched).toEqual([]);
    expect(shell.registry.all()).toEqual([...builtInModules]);
  });

  it('keeps a built-in module for its app even if the service offers a ui for it', async () => {
    const h = harness({
      [at('content')]: bundle(factoryFor({ app: 'content', slug: 'content2' })),
    });

    const shell = await loadShellModules(report(h.listed('content')), builtInModules, h.deps);

    expect(h.fetched).toEqual([]);
    expect(shell.failures).toEqual([]);
  });

  it('fetches nothing for an app with no ui entry', async () => {
    const h = harness({});

    await loadShellModules(
      report('content', 'progression', { name: 'quests', version: '2.1.0' }),
      builtInModules,
      h.deps,
    );

    expect(h.fetched).toEqual([]);
  });
});
