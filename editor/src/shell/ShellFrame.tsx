'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { NotSignedIn, restoreSession, signOut } from '@/lib/api';
import { useSession } from '@/stores/session';
import { builtInModules } from '@/modules';
import { currentCaller, type CurrentCaller } from '@/shell/caller';
import { readAppReport } from '@/shell/health';
import { moduleHost } from '@/shell/host';
import { browserLoaderDeps, loadShellModules, type ShellModules } from '@/shell/plugins';
import { createModuleRegistry, type AppReport } from '@/shell/registry';
import { ShellContext } from '@/shell/ShellContext';
import { scopeStyles } from '@/shell/styles';

/**
 * The editor shell: the session, the navigation, and the frame every module renders inside.
 *
 * Restoring the session here, once, is the visible cost of holding the access token in memory
 * only. After a reload there is no token until the refresh cookie has been exchanged, so this
 * renders a waiting state rather than bouncing to the login page — a redirect would send a
 * perfectly signed-in editor to sign in again on every refresh. Modules render only after it, so
 * none of them has to restore a session of its own.
 *
 * The navigation is computed from `/health` on every start, and so is the registry: the built-in
 * modules plus whatever installed plugins brought in their `ui/` folders. There is no cached list
 * of enabled modules to fall out of step with the service: install a plugin or switch an app off,
 * reload, and the screen is there or gone. A plugin whose screen cannot be shown is listed in the
 * rail with the reason, and nothing else is affected.
 */

// The built-in modules are checked once, at import, and a bad one throws: it shipped with the
// editor, and the first test run is the moment to hear about it.
createModuleRegistry(builtInModules);

const loaderDeps = browserLoaderDeps(moduleHost, scopeStyles);

type Started =
  | { phase: 'starting' }
  | { phase: 'failed'; message: string }
  | { phase: 'ready'; report: AppReport; caller: CurrentCaller | null; modules: ShellModules };

export function ShellFrame({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const status = useSession((state) => state.status);
  const [started, setStarted] = useState<Started>({ phase: 'starting' });

  const start = useCallback(async () => {
    setStarted({ phase: 'starting' });
    try {
      // Already signed in when arriving from the login page; a second refresh would only rotate
      // the refresh token for nothing.
      if (useSession.getState().status !== 'signed-in' && !(await restoreSession())) {
        router.push('/login');
        return;
      }
      const [report, caller] = await Promise.all([readAppReport(), currentCaller()]);
      // Never throws for a plugin's sake: each plugin's failure is in `modules.failures`.
      const modules = await loadShellModules(report, builtInModules, loaderDeps);
      setStarted({ phase: 'ready', report, caller, modules });
    } catch (thrown) {
      if (thrown instanceof NotSignedIn) {
        router.push('/login');
        return;
      }
      setStarted({
        phase: 'failed',
        message: thrown instanceof Error ? thrown.message : 'the engine could not be reached',
      });
    }
  }, [router]);

  useEffect(() => {
    void start();
  }, [start]);

  const modules = started.phase === 'ready' ? started.modules : null;
  const state = useMemo(
    () =>
      started.phase === 'ready'
        ? { registry: started.modules.registry, report: started.report, caller: started.caller }
        : null,
    [started],
  );

  // Plugin modules' scoped styles apply while their registry is the current one, and go with it.
  useEffect(() => {
    const sheets = modules?.sheets ?? [];
    if (sheets.length === 0) {
      return undefined;
    }
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, ...sheets];
    return () => {
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter(
        (sheet) => !sheets.includes(sheet),
      );
    };
  }, [modules]);

  if (started.phase === 'failed') {
    return (
      <main className="shell-message">
        <h1>The engine did not answer</h1>
        <p className="error">{started.message}</p>
        <p className="muted">
          The editor asks the engine which apps it runs before it shows any screen. Check that the
          engine is up, then try again.
        </p>
        <button type="button" onClick={() => void start()}>
          Try again
        </button>
      </main>
    );
  }

  if (!state || status !== 'signed-in') {
    return (
      <main className="shell-message">
        <p className="muted">Restoring your session…</p>
      </main>
    );
  }

  const { registry } = state;
  const failures = modules?.failures ?? [];
  const installed = modules?.installed ?? new Set<string>();
  const failed = new Set(failures.map((failure) => failure.app));
  const visible = registry.visible(state.report);
  // A plugin whose screen failed is listed with the reason, not as running without one.
  const unclaimed = registry.unclaimed(state.report).filter((app) => !failed.has(app.name));
  const current = pathname.split('/')[1] ?? '';

  return (
    <ShellContext.Provider value={state}>
      <div className="shell">
        <aside className="rail">
          <div className="rail-brand">
            <span className="rail-wordmark">Ludus</span>
            {state.caller ? (
              <span className="rail-project">Project {state.caller.project}</span>
            ) : null}
          </div>

          <nav aria-label="Apps" className="rail-nav">
            {visible.length === 0 ? (
              <p className="muted rail-note">
                This engine runs no app the editor has a screen for.
              </p>
            ) : (
              <ul>
                {visible.map(({ module, version }) => {
                  const active = current === module.slug;
                  return (
                    <li key={module.slug}>
                      <Link
                        href={registry.href(module.slug)}
                        className="rail-link"
                        aria-current={active ? 'page' : undefined}
                      >
                        <span className="rail-link-label">{module.label}</span>
                        {version ? <span className="rail-version">{version}</span> : null}
                        <span className="rail-summary">{module.summary}</span>
                        {installed.has(module.app) ? (
                          <span className="rail-origin">Installed plugin</span>
                        ) : null}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </nav>

          {failures.length > 0 ? (
            <section className="rail-failed" aria-labelledby="rail-failed-title">
              <h2 id="rail-failed-title">Screens that could not load</h2>
              <ul>
                {failures.map((failure) => (
                  <li key={failure.app}>
                    <span className="rail-failed-app">
                      <span>{failure.app}</span>
                      <span className="rail-version">{failure.version}</span>
                    </span>
                    <span className="rail-failed-reason">{failure.reason}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {unclaimed.length > 0 ? (
            <section className="rail-unclaimed" aria-labelledby="rail-unclaimed-title">
              <h2 id="rail-unclaimed-title">Running without a screen</h2>
              <ul>
                {unclaimed.map((app) => (
                  <li key={app.name}>
                    <span>{app.name}</span>
                    <span className="rail-version">{app.version}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {state.report.kind === 'unreported' ? (
            <p className="muted rail-note">
              This engine does not list its apps, so every screen the editor has is shown.
            </p>
          ) : null}

          <div className="rail-account">
            {state.caller ? (
              <p className="rail-caller">
                {state.caller.subject}
                <span className="muted"> signed in as {state.caller.role.toLowerCase()}</span>
              </p>
            ) : null}
            <button
              type="button"
              className="quiet"
              onClick={() => {
                void signOut().then(() => router.push('/login'));
              }}
            >
              Sign out
            </button>
          </div>
        </aside>
        <div className="shell-main">{children}</div>
      </div>
    </ShellContext.Provider>
  );
}
