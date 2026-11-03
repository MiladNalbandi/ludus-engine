import type { EditorModule, ModuleHost } from '@/shell/module';
import {
  createModuleRegistry,
  type AppReport,
  type LoadedApp,
  type ModuleRegistry,
} from '@/shell/registry';
import { IntegrityUnreadable, matchesIntegrity } from '@/shell/integrity';

/**
 * Loading the screens installed plugins bring, and building the registry from each `/health`.
 *
 * ```
 *   /health ─▶ apps with a `ui` entry and no built-in module
 *                │  for each, on its own:
 *                ├─ the entry is a plugin address, and the interface version is one a bundle may be
 *                ├─ GET /api/engine/plugins/<app>/<version>/ui/<entry>     (the editor's proxy)
 *                ├─ its bytes hash to the integrity recorded at install   ── else never evaluated
 *                ├─ those same bytes evaluated, from a blob: URL           (nothing fetched twice)
 *                ├─ default export (host) => module, called with the shell's React and helpers
 *                ├─ the module is the screen for the app it was installed as
 *                ├─ createModuleRegistry([...accepted, module])            the built-ins' checks
 *                └─ its styles scoped to its own screens
 *              any step failing: { app, version, reason } for the rail, and the rest carry on
 * ```
 *
 * A built-in module that is wrong still throws, at import: it shipped with the editor, and the
 * moment to find out is the first test run. A plugin's is wrong after the editor shipped, so its
 * failure stays with it — reported beside its app, while every other screen renders.
 *
 * The bytes that are checked are the bytes that run. Importing the entry's URL after checking a
 * separate fetch of it would let the second answer differ from the first.
 */

/** The `ui` entry of an app in `/health`, once read. */
export type PluginUi = { entry: string; api: number; integrity: string };

/** A plugin whose screen could not be shown, and why, in words for the rail. */
export type PluginFailure = { app: string; version: string; reason: string };

export type ShellModules = {
  registry: ModuleRegistry;
  /** Plugins whose screen could not be shown, in the order `/health` listed them. */
  failures: PluginFailure[];
  /** The apps whose module came from an installed plugin rather than with the editor. */
  installed: ReadonlySet<string>;
  /** Each plugin module's scoped styles, for the shell to adopt while this registry is current. */
  sheets: CSSStyleSheet[];
};

export type LoaderDeps = {
  host: ModuleHost;
  fetchBundle: (url: string) => Promise<Response>;
  matches: (data: ArrayBuffer, integrity: string) => Promise<boolean>;
  /** Evaluates an ES module from its bytes, resolving with its namespace. */
  evaluate: (data: ArrayBuffer, key: string) => Promise<unknown>;
  scopeStyles: (slug: string, css: string) => CSSStyleSheet;
};

/** The only interface version a bundle may be: the one whose factory hands it the shell's React. */
export const BUNDLE_API_VERSION = 2;

/** A bundle is one screen's code, not a disk. */
const MAX_BUNDLE_BYTES = 16 * 1024 * 1024;

const ENGINE_PREFIX = '/api/engine';

class PluginRefused extends Error {}

function readUi(raw: unknown): PluginUi {
  const ui = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>;
  if (
    typeof ui.entry !== 'string' ||
    typeof ui.api !== 'number' ||
    typeof ui.integrity !== 'string'
  ) {
    throw new PluginRefused(
      'the service described its screen in a form this editor does not read ' +
        '(it needs entry, api and integrity)',
    );
  }
  return { entry: ui.entry, api: ui.api, integrity: ui.integrity };
}

/**
 * The entry must be this plugin's address on the platform's UI route, so that `/health` can
 * only ever send the editor to a plugin's own `ui/` files, through its own proxy.
 */
function checkEntry(app: LoadedApp, entry: string): void {
  const parts = entry.split('/');
  const [empty, root, name, version, ui, ...file] = parts;
  const decoded = (part: string) => {
    try {
      return decodeURIComponent(part);
    } catch {
      return '..';
    }
  };
  const fine =
    empty === '' &&
    root === 'plugins' &&
    name !== undefined &&
    decoded(name) === app.name &&
    version !== undefined &&
    decoded(version) === app.version &&
    ui === 'ui' &&
    file.length > 0 &&
    file.every((part) => /^[A-Za-z0-9._~%-]+$/.test(part) && !['.', '..'].includes(decoded(part)));
  if (!fine) {
    throw new PluginRefused(
      `its screen's address, ${JSON.stringify(entry)}, is not its own plugin UI route`,
    );
  }
}

const messageOf = (thrown: unknown): string =>
  thrown instanceof Error ? thrown.message : String(thrown);

async function loadOne(app: LoadedApp, deps: LoaderDeps): Promise<EditorModule> {
  const ui = readUi(app.ui);
  if (ui.api !== BUNDLE_API_VERSION) {
    throw new PluginRefused(
      `its screen was written for module interface version ${ui.api}; ` +
        `this editor loads plugin screens written for version ${BUNDLE_API_VERSION}`,
    );
  }
  checkEntry(app, ui.entry);

  const url = `${ENGINE_PREFIX}${ui.entry}`;
  let response: Response;
  try {
    response = await deps.fetchBundle(url);
  } catch (thrown) {
    throw new PluginRefused(`its bundle could not be fetched (${messageOf(thrown)})`);
  }
  if (!response.ok) {
    throw new PluginRefused(
      `its bundle could not be fetched (GET ${ui.entry}: ${response.status})`,
    );
  }
  const type = response.headers.get('content-type') ?? '';
  if (!/^(text|application)\/javascript\b/i.test(type)) {
    throw new PluginRefused(`its bundle was served as ${type || 'no type at all'}, not JavaScript`);
  }
  const data = await response.arrayBuffer();
  if (data.byteLength > MAX_BUNDLE_BYTES) {
    throw new PluginRefused(`its bundle is ${data.byteLength} bytes; at most ${MAX_BUNDLE_BYTES}`);
  }

  let matches: boolean;
  try {
    matches = await deps.matches(data, ui.integrity);
  } catch (thrown) {
    throw new PluginRefused(
      thrown instanceof IntegrityUnreadable
        ? thrown.message
        : `its integrity could not be checked (${messageOf(thrown)})`,
    );
  }
  if (!matches) {
    throw new PluginRefused(
      'its bundle does not match the integrity recorded when it was installed, so it was not run',
    );
  }

  let namespace: unknown;
  try {
    namespace = await deps.evaluate(data, `${ui.entry} ${ui.integrity}`);
  } catch (thrown) {
    throw new PluginRefused(`its bundle failed while loading: ${messageOf(thrown)}`);
  }
  const factory = (namespace as { default?: unknown } | null)?.default;
  if (typeof factory !== 'function') {
    throw new PluginRefused(
      "its bundle's default export is not a module factory, (host) => module, as interface version 2 requires",
    );
  }

  let produced: unknown;
  try {
    produced = (factory as (host: ModuleHost) => unknown)(deps.host);
  } catch (thrown) {
    throw new PluginRefused(`its module factory threw: ${messageOf(thrown)}`);
  }
  const candidate = (
    typeof produced === 'object' && produced !== null ? produced : {}
  ) as Partial<EditorModule>;
  if (candidate.api !== BUNDLE_API_VERSION) {
    throw new PluginRefused(
      `its factory returned a module for interface version ${String(candidate.api)}, ` +
        `not ${BUNDLE_API_VERSION}`,
    );
  }
  if (candidate.app !== app.name) {
    throw new PluginRefused(
      `its module says it is the screen for '${String(candidate.app)}', but it was installed as '${app.name}'`,
    );
  }
  return produced as EditorModule;
}

export async function loadShellModules(
  report: AppReport,
  builtIns: readonly EditorModule[],
  deps: LoaderDeps,
): Promise<ShellModules> {
  const none = { failures: [], installed: new Set<string>(), sheets: [] };
  if (report.kind !== 'reported') {
    return { registry: createModuleRegistry(builtIns), ...none };
  }

  // A built-in module is the screen for its app, whatever the service says about a `ui`.
  const builtInApps = new Set(builtIns.map((module) => module.app));
  const candidates = report.apps.filter(
    (app) => app.ui !== undefined && !builtInApps.has(app.name),
  );

  // Fetched and evaluated side by side; judged against the registry one at a time, in the
  // order the service listed them, so which of two clashing plugins wins does not depend on
  // which bundle happened to arrive first.
  const outcomes = await Promise.all(
    candidates.map((app) =>
      loadOne(app, deps).then(
        (module) => ({ app, module }) as const,
        (thrown: unknown) => ({ app, reason: messageOf(thrown) }) as const,
      ),
    ),
  );

  const accepted: EditorModule[] = [...builtIns];
  const failures: PluginFailure[] = [];
  const installed = new Set<string>();
  const sheets: CSSStyleSheet[] = [];
  for (const outcome of outcomes) {
    const { app } = outcome;
    if ('reason' in outcome) {
      failures.push({ app: app.name, version: app.version, reason: outcome.reason });
      continue;
    }
    try {
      createModuleRegistry([...accepted, outcome.module]);
    } catch (thrown) {
      failures.push({
        app: app.name,
        version: app.version,
        reason: `the shell refused it: ${messageOf(thrown)}`,
      });
      continue;
    }
    let sheet: CSSStyleSheet | null = null;
    if (outcome.module.styles) {
      try {
        sheet = deps.scopeStyles(outcome.module.slug, outcome.module.styles);
      } catch (thrown) {
        failures.push({ app: app.name, version: app.version, reason: messageOf(thrown) });
        continue;
      }
    }
    accepted.push(outcome.module);
    installed.add(app.name);
    if (sheet) {
      sheets.push(sheet);
    }
  }

  return { registry: createModuleRegistry(accepted), failures, installed, sheets };
}

/**
 * Evaluated bundles, by entry and integrity. A report that names the same bytes again — every
 * reload of the shell — reuses the module rather than evaluating it a second time.
 */
const evaluated = new Map<string, Promise<unknown>>();

async function evaluateFromBytes(data: ArrayBuffer, key: string): Promise<unknown> {
  const cached = evaluated.get(key);
  if (cached) {
    return cached;
  }
  const loading = (async () => {
    const url = URL.createObjectURL(new Blob([data], { type: 'text/javascript' }));
    try {
      return (await import(/* webpackIgnore: true */ /* turbopackIgnore: true */ url)) as unknown;
    } finally {
      URL.revokeObjectURL(url);
    }
  })();
  evaluated.set(key, loading);
  loading.catch(() => evaluated.delete(key));
  return loading;
}

/** The loader as the browser runs it. */
export function browserLoaderDeps(
  host: ModuleHost,
  scopeStyles: LoaderDeps['scopeStyles'],
): LoaderDeps {
  return {
    host,
    fetchBundle: (url) => fetch(url),
    matches: (data, integrity) => matchesIntegrity(data, integrity),
    evaluate: evaluateFromBytes,
    scopeStyles,
  };
}
