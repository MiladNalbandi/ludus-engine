import type { ComponentType } from 'react';

/**
 * What a module is, to the shell. Everything the shell knows about a module is in this file.
 *
 * A module is the editor's screen for one backend app. The shell shows it only when the service
 * reports that app at `/health`, mounts it at `/<slug>`, and hands it the rest of the address. It
 * never imports a module's internals, and a module never reaches into the shell beyond the props
 * below — which is what lets a module later arrive as a built bundle from an installed plugin's
 * `ui/` folder rather than being compiled into the editor. See `docs/platform/r8.md` for what that
 * second half still has to add.
 *
 * The shape is deliberately plain data plus React components: no classes, no lifecycle hooks, no
 * registration side effects. A bundle loaded at runtime can produce a value of this type by
 * evaluating one default export, and the registry can check it before anything renders.
 */

/**
 * The version of this interface. A module declares the one it was written against, and the
 * registry refuses any other, so a plugin built for a future shell fails at registration with its
 * name in the message rather than rendering half a screen.
 */
export const MODULE_API_VERSION = 1;

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
  api: typeof MODULE_API_VERSION;
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
};
