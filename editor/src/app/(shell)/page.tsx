'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useShell } from '@/shell/ShellContext';

/** The shell's home is the first screen the engine has an app for; content, when it is loaded. */
export default function ShellHome() {
  const router = useRouter();
  const { registry, report } = useShell();
  const first = registry.visible(report)[0];

  useEffect(() => {
    if (first) {
      router.replace(registry.href(first.module.slug));
    }
  }, [first, registry, router]);

  if (first) {
    return (
      <main className="screen">
        <p className="muted">Opening {first.module.label}…</p>
      </main>
    );
  }

  return (
    <main className="screen">
      <h1>No screens to show</h1>
      <p className="muted">
        The engine is running, but none of the apps it reports has a screen in this editor. Load
        the content app on the engine to author waves and levels.
      </p>
    </main>
  );
}
