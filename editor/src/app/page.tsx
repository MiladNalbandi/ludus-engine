'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { NotSignedIn, restoreSession, signOut } from '@/lib/api';
import { engine, type CurrentCaller, type WaveLevelSummary, type WaveSummary } from '@/lib/waves';
import { useSession } from '@/stores/session';

/**
 * The catalogue: what exists, what is published, and which level players receive.
 *
 * Restoring the session on mount is the visible cost of holding the access token in memory only.
 * There is no token after a reload until the refresh cookie has been exchanged, so this renders a
 * loading state rather than bouncing to the login page — a redirect here would send a perfectly
 * signed-in editor to sign in again on every refresh.
 */
export default function CataloguePage() {
  const router = useRouter();
  const status = useSession((state) => state.status);
  const [caller, setCaller] = useState<CurrentCaller | null>(null);
  const [waves, setWaves] = useState<WaveSummary[]>([]);
  const [levels, setLevels] = useState<WaveLevelSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [me, waveList, levelList] = await Promise.all([
        engine.me(),
        engine.waves(),
        engine.waveLevels(),
      ]);
      setCaller(me);
      setWaves(waveList);
      setLevels(levelList);
      setError(null);
    } catch (thrown) {
      if (thrown instanceof NotSignedIn) {
        router.push('/login');
        return;
      }
      setError(thrown instanceof Error ? thrown.message : 'the engine could not be reached');
    }
  }, [router]);

  useEffect(() => {
    void (async () => {
      if (!(await restoreSession())) {
        router.push('/login');
        return;
      }
      await load();
    })();
  }, [load, router]);

  if (status === 'unknown') {
    return (
      <main style={{ padding: '3rem' }}>
        <p className="muted">Restoring your session…</p>
      </main>
    );
  }

  return (
    <main style={{ maxWidth: '58rem', margin: '3rem auto', padding: '0 1rem' }}>
      <header
        style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}
      >
        <div>
          <h1 style={{ marginBottom: 0 }}>Catalogue</h1>
          {caller ? (
            <p className="muted" style={{ marginTop: '0.25rem' }}>
              {caller.subject} · {caller.role} · project {caller.project}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => {
            void signOut().then(() => router.push('/login'));
          }}
        >
          Sign out
        </button>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <section style={{ marginTop: '2rem' }}>
        <h2>Waves</h2>
        {waves.length === 0 ? (
          <p className="muted">No waves yet. Import the demo set to see something here.</p>
        ) : (
          <ul className="panel" style={{ listStyle: 'none', margin: 0, padding: '0.5rem 1rem' }}>
            {waves.map((wave) => (
              <li
                key={wave.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '0.6rem 0',
                }}
              >
                <span>
                  <Link href={`/waves/${encodeURIComponent(wave.id)}`}>
                    <code>{wave.id}</code>
                  </Link>{' '}
                  <span className="muted">
                    · {wave.name} · order {wave.order}
                  </span>
                </span>
                <span>
                  <span
                    className={wave.published ? undefined : 'muted'}
                    style={{ marginRight: '0.75rem' }}
                  >
                    {wave.published ? 'published' : 'draft'}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      void (wave.published ? engine.unpublish(wave.id) : engine.publish(wave.id))
                        .then(load)
                        .catch(() => setError('that change was refused'));
                    }}
                  >
                    {wave.published ? 'Unpublish' : 'Publish'}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: '2rem' }}>
        <h2>Levels</h2>
        {levels.length === 0 ? (
          <p className="muted">No levels yet.</p>
        ) : (
          <ul className="panel" style={{ listStyle: 'none', margin: 0, padding: '0.5rem 1rem' }}>
            {levels.map((level) => (
              <li
                key={level.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '0.6rem 0',
                }}
              >
                <span>
                  {level.name}{' '}
                  <span className="muted">
                    ·{' '}
                    {/* Drafts inside a level are worth showing here: players do not receive
                        them, and this is the only place anyone can notice that. */}
                    {level.waves.filter((member) => member.published).length} of{' '}
                    {level.waves.length} reach players
                  </span>
                </span>
                <span>
                  {level.active ? (
                    <strong style={{ color: 'var(--blue)' }}>active</strong>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        void engine
                          .activateLevel(level.id)
                          .then(load)
                          .catch(() => setError('that level could not be activated'));
                      }}
                    >
                      Activate
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
