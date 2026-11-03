import { SUPPORTED_MODULE_API_VERSIONS, type EditorModule, type ModuleRoute } from '@/shell/module';

/**
 * Which modules exist, and which of them the service has the app for.
 *
 * The registry is built from a list of modules and checked as it is built: the built-in ones, and
 * since R8 the ones installed plugins brought, so the shell builds a new registry from each
 * `/health` report (see `plugins.ts`). A plugin's module meets exactly the checks a built-in one
 * does, because it goes through this same function. Visibility is then a
 * pure function of what `/health` said, recomputed whenever it is read: there is no "enabled" flag
 * to fall out of step with the service, so removing an app removes its screen the next time the
 * shell asks, and nothing else has to be told.
 */

/** One app as the service reports it. */
export type LoadedApp = {
  name: string;
  version: string;
  /**
   * An installed plugin's screen, as `/health` described it: `{entry, api, integrity}`. Kept as
   * the service sent it; the plugin loader is the one place that reads it, and a malformed one is
   * reported against that plugin rather than dropped here.
   */
  ui?: unknown;
};

/**
 * What `/health` said.
 *
 * `unreported` is an engine that answers but keeps no app registry: the Java engine, which serves
 * the whole contract as one process and has no `/health` of this shape. Every module is shown
 * against it, because every app's routes are there. It is a separate case rather than a list of
 * every app, so that the shell can say which of the two it is looking at.
 */
export type AppReport = { kind: 'reported'; apps: LoadedApp[] } | { kind: 'unreported' };

/** A module the navigation shows, with the version of its app when the service said. */
export type VisibleModule = { module: EditorModule; version: string | null };

export type Resolution =
  | { kind: 'screen'; module: EditorModule; route: ModuleRoute; params: Record<string, string> }
  | { kind: 'not-loaded'; app: string }
  | { kind: 'unknown' };

export type ModuleRegistry = {
  /** Every registered module, loaded or not, in registration order. */
  all(): readonly EditorModule[];
  /** The modules whose app the service reports, in registration order. */
  visible(report: AppReport): VisibleModule[];
  /** Apps the service reports that no module is the screen for. */
  unclaimed(report: AppReport): LoadedApp[];
  /** The screen at `/<slug>/<segments…>`, given what the service reported. */
  resolve(report: AppReport, slug: string, segments: readonly string[]): Resolution;
  /** The address of a module's screen, each segment encoded. */
  href(slug: string, ...segments: string[]): string;
};

/**
 * Addresses the shell itself answers. A module mounted at one would be unreachable: Next.js
 * matches its own routes before the shell's catch-all, so the module would simply never render.
 */
const RESERVED_SLUGS = new Set(['login', 'api', '_next', 'favicon.ico']);

const SLUG = /^[a-z0-9][a-z0-9_-]*$/;

type Segment = { literal: string } | { name: string };

type CompiledRoute = { route: ModuleRoute; segments: Segment[] };

function compile(owner: string, route: ModuleRoute): CompiledRoute {
  const parts = route.path === '' ? [] : route.path.split('/');
  const segments = parts.map((part): Segment => {
    if (part === '') {
      throw new Error(`module '${owner}' has a route with an empty segment: '${route.path}'`);
    }
    return part.startsWith(':') ? { name: part.slice(1) } : { literal: part };
  });
  return { route, segments };
}

/** Two routes with the same shape would match the same addresses, and the first would win. */
function shapeOf(compiled: CompiledRoute): string {
  return compiled.segments.map((s) => ('literal' in s ? s.literal : ':')).join('/');
}

const isText = (value: unknown): value is string => typeof value === 'string';

/**
 * The shape, checked at runtime. A built-in module is held to it by the compiler; a plugin's is a
 * value some bundle returned, and a field that is missing must be a refusal naming it — not a
 * `TypeError` from deep inside the registry, or worse, a screen that renders `undefined`.
 */
function checkShape(candidate: unknown): asserts candidate is EditorModule {
  if (typeof candidate !== 'object' || candidate === null) {
    throw new Error(
      `a module must be an object, not ${candidate === null ? 'null' : typeof candidate}`,
    );
  }
  const shape = candidate as Record<string, unknown>;
  const name = isText(shape.slug) ? `module '${shape.slug}'` : 'a module';
  if (typeof shape.api !== 'number') {
    throw new Error(`${name} does not say which module interface version it was written for`);
  }
  for (const field of ['app', 'slug', 'label', 'summary'] as const) {
    if (!isText(shape[field])) {
      throw new Error(`${name} has no ${field}; it must be text`);
    }
  }
  if (!Array.isArray(shape.routes)) {
    throw new Error(`${name} has no list of routes`);
  }
  for (const route of shape.routes as unknown[]) {
    const entry = (typeof route === 'object' && route !== null ? route : {}) as Record<
      string,
      unknown
    >;
    const screen = entry.screen;
    if (
      !isText(entry.path) ||
      !isText(entry.title) ||
      !(typeof screen === 'function' || (typeof screen === 'object' && screen !== null))
    ) {
      throw new Error(`${name} has a route without a path, a title and a screen component`);
    }
  }
  if (shape.styles !== undefined && !isText(shape.styles)) {
    throw new Error(`${name} has styles that are not CSS text`);
  }
}

function check(module: EditorModule): CompiledRoute[] {
  checkShape(module);
  if (!SUPPORTED_MODULE_API_VERSIONS.includes(module.api)) {
    throw new Error(
      `module '${module.slug}' was written for module interface version ${String(module.api)}; ` +
        `this shell implements interface versions ${SUPPORTED_MODULE_API_VERSIONS.join(' and ')}`,
    );
  }
  if (module.api < 2 && module.styles !== undefined) {
    throw new Error(
      `module '${module.slug}' carries styles, which need module interface version 2`,
    );
  }
  if (RESERVED_SLUGS.has(module.slug)) {
    throw new Error(`module slug '${module.slug}' is reserved by the shell`);
  }
  if (!SLUG.test(module.slug)) {
    throw new Error(
      `module for app '${module.app}' has slug '${module.slug}', which is not one lowercase URL ` +
        'segment of letters, digits, - and _',
    );
  }

  const compiled = module.routes.map((route) => compile(module.slug, route));
  if (!compiled.some((entry) => entry.segments.length === 0)) {
    throw new Error(`module '${module.slug}' has no home screen (a route with the path '')`);
  }
  const shapes = new Set<string>();
  for (const entry of compiled) {
    const shape = shapeOf(entry);
    if (shapes.has(shape)) {
      throw new Error(
        `module '${module.slug}' has two routes shaped '${shape}'; the second could never match`,
      );
    }
    shapes.add(shape);
  }
  return compiled;
}

/**
 * How well a route matches, or null if it does not: the number of literal segments, so that
 * `levels/new` beats `levels/:id` whichever was listed first.
 */
function score(
  compiled: CompiledRoute,
  segments: readonly string[],
): { literals: number; params: Record<string, string> } | null {
  if (compiled.segments.length !== segments.length) {
    return null;
  }
  const params: Record<string, string> = {};
  let literals = 0;
  for (const [index, segment] of compiled.segments.entries()) {
    const actual = segments[index] ?? '';
    if ('literal' in segment) {
      if (segment.literal !== actual) {
        return null;
      }
      literals += 1;
    } else {
      try {
        params[segment.name] = decodeURIComponent(actual);
      } catch {
        // A malformed escape is an address nobody linked to; it matches nothing.
        return null;
      }
    }
  }
  return { literals, params };
}

export function createModuleRegistry(modules: readonly EditorModule[]): ModuleRegistry {
  const byApp = new Map<string, EditorModule>();
  const bySlug = new Map<string, { module: EditorModule; routes: CompiledRoute[] }>();

  for (const candidate of modules) {
    const routes = check(candidate);
    if (byApp.has(candidate.app)) {
      throw new Error(
        `two modules claim app '${candidate.app}'; only one screen can be its screen`,
      );
    }
    if (bySlug.has(candidate.slug)) {
      throw new Error(`two modules are mounted at slug '${candidate.slug}'`);
    }
    byApp.set(candidate.app, candidate);
    bySlug.set(candidate.slug, { module: candidate, routes });
  }

  const ordered = [...modules];

  function versionOf(report: AppReport, app: string): string | null | undefined {
    if (report.kind === 'unreported') {
      return null;
    }
    return report.apps.find((loaded) => loaded.name === app)?.version;
  }

  return {
    all: () => ordered,

    visible(report) {
      return ordered.flatMap((module) => {
        const version = versionOf(report, module.app);
        return version === undefined ? [] : [{ module, version }];
      });
    },

    unclaimed(report) {
      return report.kind === 'unreported'
        ? []
        : report.apps.filter((loaded) => !byApp.has(loaded.name));
    },

    resolve(report, slug, segments) {
      const entry = bySlug.get(slug);
      if (!entry) {
        return { kind: 'unknown' };
      }
      if (versionOf(report, entry.module.app) === undefined) {
        return { kind: 'not-loaded', app: entry.module.app };
      }
      let best: { route: ModuleRoute; literals: number; params: Record<string, string> } | null =
        null;
      for (const compiled of entry.routes) {
        const found = score(compiled, segments);
        if (found && (!best || found.literals > best.literals)) {
          best = { route: compiled.route, ...found };
        }
      }
      return best
        ? { kind: 'screen', module: entry.module, route: best.route, params: best.params }
        : { kind: 'unknown' };
    },

    href(slug, ...segments) {
      return ['', slug, ...segments.map((segment) => encodeURIComponent(segment))].join('/');
    },
  };
}
