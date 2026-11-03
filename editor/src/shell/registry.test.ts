import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ComponentType } from 'react';
import { MODULE_API_VERSION, type EditorModule, type ModuleScreenProps } from '@/shell/module';
import { createModuleRegistry, type AppReport } from '@/shell/registry';
import { builtInModules } from '@/modules';

/**
 * The rule the shell exists to keep: a screen is shown only for an app the service says it loaded.
 *
 * The service's `/health` is the one place that knows which apps are running, so the navigation is
 * computed from it rather than from a list compiled into the editor. A list compiled in would show
 * an inventory screen against a service with inventory switched off, and every call that screen
 * made would fail with a 404 that reads like a bug in the screen.
 */
const Screen: ComponentType<ModuleScreenProps> = () => null;

function module(
  overrides: Partial<EditorModule> & Pick<EditorModule, 'app' | 'slug'>,
): EditorModule {
  return {
    api: MODULE_API_VERSION,
    label: overrides.app,
    summary: `the ${overrides.app} screens`,
    routes: [{ path: '', title: 'Home', screen: Screen }],
    ...overrides,
  };
}

function reported(...names: string[]): AppReport {
  return { kind: 'reported', apps: names.map((name) => ({ name, version: '1.0.0' })) };
}

const content = module({ app: 'content', slug: 'content', label: 'Content' });
const inventory = module({ app: 'inventory', slug: 'inventory', label: 'Inventory' });
const economy = module({ app: 'economy', slug: 'economy', label: 'Economy' });

describe('which modules the navigation shows', () => {
  it('shows a module only when its app is in /health', () => {
    const registry = createModuleRegistry([content, inventory, economy]);

    const visible = registry.visible(reported('content', 'economy'));

    expect(visible.map((entry) => entry.module.slug)).toEqual(['content', 'economy']);
  });

  it('removes a module when its app is removed from /health', () => {
    const registry = createModuleRegistry([content, inventory]);

    expect(registry.visible(reported('content', 'inventory')).map((e) => e.module.app)).toEqual([
      'content',
      'inventory',
    ]);
    expect(registry.visible(reported('content')).map((e) => e.module.app)).toEqual(['content']);
  });

  it('shows nothing when the service reports no apps at all', () => {
    const registry = createModuleRegistry([content, inventory]);

    expect(registry.visible(reported())).toEqual([]);
  });

  it('carries the version the service reported, so the navigation can show what is running', () => {
    const registry = createModuleRegistry([content]);

    const [entry] = registry.visible({
      kind: 'reported',
      apps: [{ name: 'content', version: '2.3.1' }],
    });

    expect(entry?.version).toBe('2.3.1');
  });

  it('keeps the registration order, not the order /health happens to list apps in', () => {
    const registry = createModuleRegistry([content, inventory, economy]);

    const visible = registry.visible(reported('economy', 'inventory', 'content'));

    expect(visible.map((entry) => entry.module.slug)).toEqual(['content', 'inventory', 'economy']);
  });

  it('lists loaded apps that have no screen, rather than hiding that they are running', () => {
    const registry = createModuleRegistry([content]);

    expect(registry.unclaimed(reported('content', 'progression', 'map_editor'))).toEqual([
      { name: 'progression', version: '1.0.0' },
      { name: 'map_editor', version: '1.0.0' },
    ]);
  });

  it('shows every module when the engine does not report its apps', () => {
    // The Java engine answers /health with 401: it has no app registry, and serves the whole
    // contract as one process. Hiding every screen from it would leave an editor with nothing on
    // it pointed at an engine that serves all of them.
    const registry = createModuleRegistry([content, inventory]);

    expect(registry.visible({ kind: 'unreported' }).map((e) => e.module.slug)).toEqual([
      'content',
      'inventory',
    ]);
    expect(registry.visible({ kind: 'unreported' })[0]?.version).toBeNull();
    expect(registry.unclaimed({ kind: 'unreported' })).toEqual([]);
  });
});

describe('what the registry refuses', () => {
  it('refuses two modules for one app', () => {
    expect(() =>
      createModuleRegistry([content, module({ app: 'content', slug: 'content_two' })]),
    ).toThrow(/app 'content'/);
  });

  it('refuses two modules at one address', () => {
    expect(() =>
      createModuleRegistry([content, module({ app: 'other', slug: 'content' })]),
    ).toThrow(/slug 'content'/);
  });

  it('refuses an address the shell itself owns', () => {
    for (const slug of ['login', 'api', '_next']) {
      expect(() => createModuleRegistry([module({ app: 'x', slug })])).toThrow(/reserved/);
    }
  });

  it('refuses an address that is not one URL segment', () => {
    for (const slug of ['', 'two/parts', 'Upper', 'with space']) {
      expect(() => createModuleRegistry([module({ app: 'x', slug })])).toThrow(/slug/);
    }
  });

  it('refuses a module written for another version of the module interface', () => {
    expect(() =>
      createModuleRegistry([
        { ...content, api: (MODULE_API_VERSION + 1) as typeof MODULE_API_VERSION },
      ]),
    ).toThrow(/interface version/);
  });

  it('accepts modules written for interface version 1 and version 2 side by side', () => {
    const registry = createModuleRegistry([
      { ...content, api: 1 },
      { ...inventory, api: 2, styles: '.panel { color: red }' },
    ]);

    expect(registry.all().map((entry) => entry.api)).toEqual([1, 2]);
  });

  it('refuses styles on a version 1 module, which predates them', () => {
    expect(() => createModuleRegistry([{ ...content, api: 1, styles: '.x {}' }])).toThrow(
      /styles, which need module interface version 2/,
    );
  });

  it('refuses a module missing a field, naming the field rather than failing inside', () => {
    // A plugin's module is whatever its bundle returned; the compiler never saw it.
    const loose = (value: unknown) => value as EditorModule;
    expect(() => createModuleRegistry([loose(null)])).toThrow(/must be an object/);
    expect(() => createModuleRegistry([loose({ ...content, label: undefined })])).toThrow(
      /no label/,
    );
    expect(() => createModuleRegistry([loose({ ...content, routes: 'home' })])).toThrow(
      /no list of routes/,
    );
    expect(() =>
      createModuleRegistry([loose({ ...content, routes: [{ path: '', title: 'Home' }] })]),
    ).toThrow(/screen component/);
    expect(() => createModuleRegistry([loose({ ...content, api: '2' })])).toThrow(
      /interface version/,
    );
  });

  it('refuses a module with no home screen', () => {
    expect(() =>
      createModuleRegistry([
        module({
          app: 'x',
          slug: 'x',
          routes: [{ path: 'things/:id', title: 'Thing', screen: Screen }],
        }),
      ]),
    ).toThrow(/home/);
  });

  it('refuses two routes with one pattern', () => {
    expect(() =>
      createModuleRegistry([
        module({
          app: 'x',
          slug: 'x',
          routes: [
            { path: '', title: 'Home', screen: Screen },
            { path: 'a/:id', title: 'A', screen: Screen },
            { path: 'a/:other', title: 'B', screen: Screen },
          ],
        }),
      ]),
    ).toThrow(/route/);
  });
});

describe('resolving an address to a screen', () => {
  const Waves: ComponentType<ModuleScreenProps> = () => null;
  const Level: ComponentType<ModuleScreenProps> = () => null;
  const NewLevel: ComponentType<ModuleScreenProps> = () => null;
  const registry = createModuleRegistry([
    module({
      app: 'content',
      slug: 'content',
      routes: [
        { path: '', title: 'Catalogue', screen: Screen },
        { path: 'waves/:id', title: 'Wave', screen: Waves },
        // Listed pattern-first on purpose: a literal segment must win whatever the order.
        { path: 'levels/:id', title: 'Level', screen: Level },
        { path: 'levels/new', title: 'New level', screen: NewLevel },
      ],
    }),
    inventory,
  ]);

  it('finds the home screen at the module address', () => {
    const found = registry.resolve(reported('content'), 'content', []);

    expect(found.kind).toBe('screen');
    expect(found.kind === 'screen' && found.route.screen).toBe(Screen);
  });

  it('passes the named segments, decoded', () => {
    const found = registry.resolve(reported('content'), 'content', ['waves', 'demo%20one']);

    expect(found.kind === 'screen' && found.route.screen).toBe(Waves);
    expect(found.kind === 'screen' && found.params).toEqual({ id: 'demo one' });
  });

  it('prefers a literal segment over a named one, whatever the order', () => {
    const found = registry.resolve(reported('content'), 'content', ['levels', 'new']);
    expect(found.kind === 'screen' && found.route.screen).toBe(NewLevel);

    const other = registry.resolve(reported('content'), 'content', ['levels', 'lvl_1']);
    expect(other.kind === 'screen' && other.route.screen).toBe(Level);
  });

  it('says a module is not loaded, rather than showing a screen whose app is off', () => {
    const found = registry.resolve(reported('content'), 'inventory', []);

    expect(found).toEqual({ kind: 'not-loaded', app: 'inventory' });
  });

  it('says an address is unknown when no module or route claims it', () => {
    expect(registry.resolve(reported('content'), 'nowhere', [])).toEqual({ kind: 'unknown' });
    expect(registry.resolve(reported('content'), 'content', ['waves'])).toEqual({
      kind: 'unknown',
    });
    expect(registry.resolve(reported('content'), 'content', ['waves', 'a', 'b'])).toEqual({
      kind: 'unknown',
    });
  });

  it('builds a module-relative address, encoding each segment', () => {
    expect(registry.href('content')).toBe('/content');
    expect(registry.href('content', 'waves', 'a b/c')).toBe('/content/waves/a%20b%2Fc');
  });
});

describe('the modules this editor ships', () => {
  it('is a valid registry', () => {
    expect(() => createModuleRegistry(builtInModules)).not.toThrow();
  });

  it('names only apps the service ships, by the name in their manifest', () => {
    // A module whose app name is misspelt is a screen that never appears, with nothing to say why.
    const apps = resolve(__dirname, '..', '..', '..', 'service', 'src', 'wavemaker', 'apps');
    const shipped = readdirSync(apps, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .flatMap((entry) => {
        try {
          const manifest = readFileSync(resolve(apps, entry.name, 'manifest.toml'), 'utf8');
          const name = /^name\s*=\s*"([^"]+)"/m.exec(manifest)?.[1];
          return name ? [name] : [];
        } catch {
          return [];
        }
      });

    for (const builtIn of builtInModules) {
      expect(shipped).toContain(builtIn.app);
    }
  });

  it('has a screen for content, inventory, economy, media and leaderboard', () => {
    expect(builtInModules.map((entry) => entry.app).sort()).toEqual([
      'content',
      'economy',
      'inventory',
      'leaderboard',
      'media',
    ]);
  });

  it('gives content the level authoring addresses', () => {
    const registry = createModuleRegistry(builtInModules);
    const at = (...segments: string[]) => {
      const found = registry.resolve(reported('content'), 'content', segments);
      return found.kind === 'screen' ? found.route.title : found.kind;
    };

    expect(at('levels', 'new')).toBe('New level');
    expect(at('levels', 'lvl_1')).toBe('Level');
    expect(at('waves', 'w1')).toBe('Wave');
  });

  it('puts content first, so signing in lands on the catalogue', () => {
    const registry = createModuleRegistry(builtInModules);

    expect(registry.visible(reported('media', 'content', 'economy'))[0]?.module.app).toBe(
      'content',
    );
  });
});
