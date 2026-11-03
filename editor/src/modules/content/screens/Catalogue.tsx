'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { NotSignedIn } from '@/lib/api';
import type { ModuleScreenProps } from '@/shell/module';
import { engine, type WaveLevelSummary, type WaveSummary } from '@/modules/content/waves';

/**
 * The catalogue: what exists, what is published, and which level players receive.
 *
 * The shell restores the session before any module renders, so this screen starts signed in and
 * only has to handle the session expiring while it is open. Who is signed in, and signing out,
 * moved to the shell with it.
 */
export default function CatalogueScreen({ href }: ModuleScreenProps) {
  const router = useRouter();
  const [waves, setWaves] = useState<WaveSummary[]>([]);
  const [levels, setLevels] = useState<WaveLevelSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [waveList, levelList] = await Promise.all([engine.waves(), engine.waveLevels()]);
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
    void load();
  }, [load]);

  return (
    <main className="screen" style={{ maxWidth: '58rem' }}>
      <header>
        <h1 style={{ marginBottom: 0 }}>Catalogue</h1>
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
                  <Link href={href('waves', wave.id)}>
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
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <h2>Levels</h2>
          <Link href={href('levels', 'new')} className="button-link">
            New level
          </Link>
        </div>
        {levels.length === 0 ? (
          <p className="muted">No levels yet. Create one to put waves in the order players meet them.</p>
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
                  <Link href={href('levels', level.id)}>{level.name}</Link>{' '}
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
