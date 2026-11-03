'use client';

import { useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useShell } from '@/shell/ShellContext';

/**
 * Renders the module screen at the current address, or says why there is none.
 *
 * This is the only route the shell owns for modules: `/<slug>/<rest…>`. A module's own routes are
 * matched here from its declaration, not from files under `src/app`, which is what will let a
 * module from a plugin bring screens without adding a file to this app.
 */
export function ModuleOutlet() {
  const { registry, report } = useShell();
  const params = useParams<{ module: string; path?: string[] }>();
  const slug = params.module;
  const rest = useMemo(() => params.path ?? [], [params.path]);

  const found = registry.resolve(report, slug, rest);
  const title = found.kind === 'screen' ? found.route.title : null;

  useEffect(() => {
    if (title) {
      document.title = `${title} | Ludus editor`;
    }
  }, [title]);

  const href = useMemo(
    () =>
      (...segments: string[]) =>
        registry.href(slug, ...segments),
    [registry, slug],
  );

  if (found.kind === 'not-loaded') {
    return (
      <main className="screen">
        <h1>This app is not running</h1>
        <p className="muted">
          The engine does not report the <code>{found.app}</code> app, so its screen is switched
          off. Load the app on the engine and reload this page to see it again.
        </p>
      </main>
    );
  }

  if (found.kind === 'unknown') {
    return (
      <main className="screen">
        <h1>Nothing lives at this address</h1>
        <p className="muted">
          No screen in the editor matches it. <Link href="/">Go to the first screen</Link>.
        </p>
      </main>
    );
  }

  // Keyed by the address, so moving from one level to another starts the screen afresh instead of
  // showing the previous level's fields until the next one loads.
  const Screen = found.route.screen;
  return <Screen key={`${slug}/${rest.join('/')}`} params={found.params} href={href} />;
}
