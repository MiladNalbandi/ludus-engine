import type { ComponentType } from 'react';
import type * as ReactNamespace from 'react';
import type * as Api from '@/lib/api';
import type * as Requests from '@/lib/requests';
import type * as SharedUi from '@/lib/ui';
import type * as EngineCall from '@/lib/useEngineCall';

/**
 * What a module is, to the shell. Everything the shell knows about a module is in this file.
 *
 * A module is the editor's screen for one backend app. The shell shows it only when the service
 * reports that app at `/health`, mounts it at `/<slug>`, and hands it the rest of the address. It
 * never imports a module's internals, and a module never reaches into the shell beyond the props
 * below.
 *
 * A module arrives one of two ways. A built-in one is compiled into the editor and is a plain
 * value of `EditorModule`. A plugin's arrives at runtime as a bundle from its `ui/` folder: one ES
 * module whose default export is a `ModuleFactory`, which the shell calls with a `ModuleHost` —
 * the shell's own React and request helpers — and which returns an `EditorModule`. Both go through
 * the same registry checks. See `docs/platform/r8.md`.
 *
 * The shape is deliberately plain data plus React components: no classes, no lifecycle hooks, no
 * registration side effects.
 */

/**
 * The version of this interface. A module declares the one it was written against, and the
 * registry refuses any version it does not implement, so a plugin built for a future shell fails
 * at registration with its name in the message rather than rendering half a screen.
 *
 * Version 2 added two things to version 1, and took nothing away: a module may come from a
 * `ModuleFactory` given a `ModuleHost`, and it may carry `styles`. A version 1 module is still
 * accepted as it is. A plugin's bundle must be version 2, because it is the factory that gives it
 * the shell's React — a bundle with its own copy would break every hook it used.
 */
export const MODULE_API_VERSION = 2;

/** Every interface version this shell implements. */
export const SUPPORTED_MODULE_API_VERSIONS: readonly number[] = [1, 2];

export type ModuleApiVersion = 1 | 2;

/** What the shell passes every screen. */
export type ModuleScreenProps = {
  /** The decoded values of the route's `:name` segments. */
  params: Readonly<Record<string, string>>;
  /**
   * An address inside this module: `href()` is the module's home, `href('waves', id)` one of its
   * routes. Each segment is encoded here. A module never writes its own slug into a link, so the
   * shell can mount it anywhere.
   */
  href: (...segments: string[]) => string;
};

export type ModuleRoute = {
  /**
   * The address inside the module, as `/`-separated segments: `''` for the home screen, a literal
   * such as `schema`, or a named segment such as `waves/:id`. A literal segment beats a named one
   * at the same position, whatever order the routes are listed in.
   */
  path: string;
  /** The screen's name, used for the document title. */
  title: string;
  screen: ComponentType<ModuleScreenProps>;
};

export type EditorModule = {
  /** The interface version this module was written against. */
  api: ModuleApiVersion;
  /** The backend app this is the screen for, by the name the service reports at `/health`. */
  app: string;
  /** The URL segment the module is mounted at: lowercase letters, digits, `-` and `_`. */
  slug: string;
  /** The name in the navigation. */
  label: string;
  /** One line on what the screens are for, shown under the label. */
  summary: string;
  /** The module's screens. Exactly one has the path `''`. */
  routes: readonly ModuleRoute[];
  /**
   * Version 2: CSS for this module's screens. The shell scopes every rule to them, so a module can
   * restyle the shell's own classes on its screens and nowhere else. `@import`, `@font-face`,
   * `@keyframes` and anything else that cannot be scoped is refused.
   */
  styles?: string;
};

/**
 * What the shell hands a plugin's factory: the same things a built-in module imports from
 * `src/lib/`, so a plugin's screen is written the way a built-in one is.
 */
export type ModuleHost = {
  /** The interface version the shell is calling the factory as. */
  api: typeof MODULE_API_VERSION;
  /** The shell's React. A screen must use this one, never a copy of its own. */
  React: typeof ReactNamespace;
  /** Calls to the engine as the signed-in author: `fetch` is `apiFetch`, the rest `requests.ts`. */
  engine: {
    fetch: typeof Api.apiFetch;
    json: typeof Api.apiJson;
    send: typeof Requests.send;
    sendJson: typeof Requests.sendJson;
    sendText: typeof Requests.sendText;
    jsonBody: typeof Requests.jsonBody;
    segment: typeof Requests.segment;
    Refused: typeof Requests.Refused;
    NotSignedIn: typeof Api.NotSignedIn;
  };
  useEngineCall: typeof EngineCall.useEngineCall;
  formatMoment: typeof EngineCall.formatMoment;
  /** The small pieces the built-in screens share. */
  ui: {
    ConfirmDelete: typeof SharedUi.ConfirmDelete;
    Problems: typeof SharedUi.Problems;
    EngineError: typeof SharedUi.EngineError;
    SubNav: typeof SharedUi.SubNav;
  };
};

/** The default export of a plugin's bundle. */
export type ModuleFactory = (host: ModuleHost) => EditorModule;
