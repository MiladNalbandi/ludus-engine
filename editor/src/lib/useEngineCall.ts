'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { NotSignedIn } from '@/lib/api';

/**
 * Runs an engine call for a screen, and turns its failure into something the screen can show.
 *
 * An expired session goes to the login page, as every screen did before; any other failure becomes
 * the message the engine gave. `run` resolves to `undefined` on failure, so a caller can carry on
 * with `if (result)` rather than wrapping every call in its own try.
 */
export function useEngineCall() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(
    async <T>(work: () => Promise<T>): Promise<T | undefined> => {
      setBusy(true);
      try {
        const result = await work();
        setError(null);
        return result;
      } catch (thrown) {
        if (thrown instanceof NotSignedIn) {
          router.push('/login');
          return undefined;
        }
        setError(thrown instanceof Error ? thrown.message : 'the engine could not be reached');
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [router],
  );

  return { error, setError, busy, run };
}

/** A date as the author's own clock reads it. */
export function formatMoment(iso: string | null | undefined): string {
  if (!iso) {
    return '';
  }
  const moment = new Date(iso);
  return Number.isNaN(moment.getTime())
    ? iso
    : moment.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
