'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ModuleScreenProps } from '@/shell/module';
import { useEngineCall } from '@/lib/useEngineCall';
import { ConfirmDelete, EngineError, Problems } from '@/lib/ui';
import { engine, type WaveLevelSummary, type WaveSummary } from '@/modules/content/waves';
import {
  addWave,
  checkLevel,
  draftOfLevel,
  levels,
  moveWave,
  removeWaveAt,
  type LevelDraft,
} from '@/modules/content/levels';

/**
 * Creating or editing one level: its name, its description, and its waves in play order.
 *
 * The order is edited locally and sent whole, because an update replaces the list wholesale. Drafts
 * may sit in a level — players simply do not receive them — so each row says which it is, the same
 * fact the catalogue counts.
 */
const BLANK: LevelDraft = { name: '', description: '', waves: [] };

export default function LevelEditorScreen({ params, href }: ModuleScreenProps) {
  const router = useRouter();
  const id = params.id;
  const { error, busy, run } = useEngineCall();
  const [waves, setWaves] = useState<WaveSummary[]>([]);
  const [stored, setStored] = useState<WaveLevelSummary | null>(null);
  const [draft, setDraft] = useState<LevelDraft>(BLANK);
  const [problems, setProblems] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [adding, setAdding] = useState('');
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    const result = await run(() =>
      Promise.all([engine.waves(), id ? levels.get(id) : Promise.resolve(null)]),
    );
    if (result) {
      const [waveList, level] = result;
      setWaves(waveList);
      setStored(level);
      setDraft(level ? draftOfLevel(level) : BLANK);
    }
    setLoaded(true);
  }, [id, run]);

  useEffect(() => {
    void load();
  }, [load]);

  const byId = useMemo(() => new Map(waves.map((wave) => [wave.id, wave])), [waves]);
  const addable = waves.filter((wave) => !draft.waves.includes(wave.id));
  const choice = addable.some((wave) => wave.id === adding) ? adding : (addable[0]?.id ?? '');

  function change(next: LevelDraft) {
    setDraft(next);
    setSaved(false);
  }

  async function save() {
    const found = checkLevel(draft);
    setProblems(found);
    if (found.length > 0) {
      return;
    }
    const result = await run(() => (id ? levels.update(id, draft) : levels.create(draft)));
    if (!result) {
      return;
    }
    setStored(result);
    setDraft(draftOfLevel(result));
    setSaved(true);
    if (!id) {
      router.replace(href('levels', result.id));
    }
  }

  async function remove() {
    if (!id) {
      return;
    }
    const done = await run(async () => {
      await levels.remove(id);
      return true;
    });
    if (done) {
      router.push(href());
    }
  }

  if (!loaded) {
    return (
      <main className="screen">
        <p className="muted">Loading…</p>
      </main>
    );
  }

  if (id && !stored) {
    return (
      <main className="screen">
        <h1>Level not found</h1>
        <EngineError message={error} />
        <Link href={href()}>Back to the catalogue</Link>
      </main>
    );
  }

  const title = stored ? stored.name : 'New level';

  return (
    <main className="screen" style={{ maxWidth: '46rem' }}>
      <header className="screen-header">
        <div>
          <h1>{title}</h1>
          <p className="screen-lede">
            {stored?.active
              ? 'This is the active level: players receive its published waves now.'
              : 'Waves play in the order listed here. Activate a level from the catalogue.'}
          </p>
        </div>
        <Link href={href()}>Back to the catalogue</Link>
      </header>

      <form
        className="form-stack"
        style={{ marginTop: '1.75rem' }}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <div>
          <label htmlFor="level-name">Name</label>
          <input
            id="level-name"
            value={draft.name}
            maxLength={255}
            onChange={(event) => change({ ...draft, name: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="level-description">Description</label>
          <input
            id="level-description"
            value={draft.description}
            placeholder="Optional"
            onChange={(event) => change({ ...draft, description: event.target.value })}
          />
        </div>

        <section aria-labelledby="level-waves-title" className="panel">
          <h2 id="level-waves-title">Waves in play order</h2>
          {draft.waves.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>
              No waves yet. Add the first one below; a level can also be saved empty.
            </p>
          ) : (
            <ol className="level-waves">
              {draft.waves.map((waveId, index) => {
                const wave = byId.get(waveId);
                return (
                  <li key={waveId}>
                    {/* The list itself tells a screen reader the position; this is for the eye. */}
                    <span className="level-position" aria-hidden="true">
                      {index + 1}
                    </span>
                    <span className="level-wave-name">
                      <code>{waveId}</code>
                      <span className="muted">
                        {wave ? ` ${wave.name}, ${wave.published ? 'published' : 'draft'}` : ' not in the catalogue'}
                      </span>
                    </span>
                    <span className="actions">
                      <button
                        type="button"
                        className="quiet small"
                        aria-label={`Move ${waveId} earlier`}
                        disabled={index === 0}
                        onClick={() => change({ ...draft, waves: moveWave(draft.waves, index, -1) })}
                      >
                        Earlier
                      </button>
                      <button
                        type="button"
                        className="quiet small"
                        aria-label={`Move ${waveId} later`}
                        disabled={index === draft.waves.length - 1}
                        onClick={() => change({ ...draft, waves: moveWave(draft.waves, index, 1) })}
                      >
                        Later
                      </button>
                      <button
                        type="button"
                        className="quiet small"
                        aria-label={`Remove ${waveId} from the level`}
                        onClick={() => change({ ...draft, waves: removeWaveAt(draft.waves, index) })}
                      >
                        Remove
                      </button>
                    </span>
                  </li>
                );
              })}
            </ol>
          )}

          {addable.length > 0 ? (
            <div className="level-add">
              <div style={{ flex: 1 }}>
                <label htmlFor="level-add-wave">Add a wave</label>
                <select
                  id="level-add-wave"
                  value={choice}
                  onChange={(event) => setAdding(event.target.value)}
                >
                  {addable.map((wave) => (
                    <option key={wave.id} value={wave.id}>
                      {wave.id} ({wave.name})
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="quiet"
                disabled={!choice}
                onClick={() => change({ ...draft, waves: addWave(draft.waves, choice) })}
              >
                Add to the end
              </button>
            </div>
          ) : waves.length > 0 ? (
            <p className="notice" style={{ marginBottom: 0 }}>
              Every wave in the catalogue is in this level.
            </p>
          ) : null}
        </section>

        <Problems problems={problems} />
        <EngineError message={error} />

        <div className="actions" style={{ justifyContent: 'space-between' }}>
          <span className="actions">
            <button type="submit" disabled={busy}>
              {busy ? 'Saving…' : id ? 'Save level' : 'Create level'}
            </button>
            {saved ? (
              <span className="notice" role="status">
                Saved.
              </span>
            ) : null}
          </span>
          {stored ? <ConfirmDelete what={stored.name} onConfirm={() => void remove()} /> : null}
        </div>
      </form>
    </main>
  );
}
