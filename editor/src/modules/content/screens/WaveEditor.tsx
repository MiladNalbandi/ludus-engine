'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { NotSignedIn, apiFetch } from '@/lib/api';
import type { ModuleScreenProps } from '@/shell/module';
import type { MovementType, Wave } from '@/lib/wave-schema';
import { registerBuiltInMovements } from '@/modules/content/simulator/movements';
import { simulatorRegistry } from '@/modules/content/simulator/registry';
import { registerBuiltInBehaviourEditors } from '@/modules/content/components/behaviour/panels';
import { behaviorEditorRegistry } from '@/modules/content/components/behaviour/registry';
import { Timeline } from '@/modules/content/components/Timeline';
import { Inspector } from '@/modules/content/components/Inspector';
import { Preview } from '@/modules/content/components/Preview';
import { useEditor } from '@/modules/content/stores/editor';

/**
 * Registration happens once, at module load.
 *
 * Guarded rather than unguarded because Next's dev server re-evaluates a module on hot reload, and
 * the registries refuse a second registration on purpose — a duplicate there means two behaviours
 * claim one type and whichever loaded last silently wins. Refusing is right; crashing the dev
 * server on every save is not.
 */
if (simulatorRegistry.registered().length === 0) {
  registerBuiltInMovements();
}
if (behaviorEditorRegistry.registered().length === 0) {
  registerBuiltInBehaviourEditors();
}

const MOVEMENT_TYPES: MovementType[] = [
  'patrol',
  'orbit',
  'teleport',
  'dash',
  'wait',
  'jump',
  'zigzag',
  'spiral',
  'cross',
  'hide',
  'despawn',
];

export default function WaveEditorScreen({ params, href }: ModuleScreenProps) {
  const id = params.id ?? '';
  const router = useRouter();

  const wave = useEditor((state) => state.wave);
  const timelines = useEditor((state) => state.timelines);
  const selectedRule = useEditor((state) => state.selectedRule);
  const playhead = useEditor((state) => state.playhead);
  const dirty = useEditor((state) => state.dirty);
  const load = useEditor((state) => state.load);
  const selectRule = useEditor((state) => state.selectRule);
  const setPlayhead = useEditor((state) => state.setPlayhead);
  const addBlock = useEditor((state) => state.addBlock);

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const open = useCallback(async () => {
    try {
      // GET on the admin route returns the stored document itself, draft or not -- the same bytes
      // the engine received. Nothing else in the editor parses a wave document.
      const response = await apiFetch(`/api/v1/admin/waves/${encodeURIComponent(id)}`);
      if (response.status === 404) {
        setError('There is no wave with that id.');
        return;
      }
      // Parsed here and nowhere else. The document is sent back as the store's object, and the
      // engine stores the bytes it receives -- which is why the store never rewrites the parts it
      // does not edit.
      load((await response.json()) as Wave);
    } catch (thrown) {
      if (thrown instanceof NotSignedIn) {
        router.push('/login');
        return;
      }
      setError(thrown instanceof Error ? thrown.message : 'the wave could not be loaded');
    }
  }, [id, load, router]);

  // The shell has restored the session before this screen renders.
  useEffect(() => {
    void open();
  }, [open]);

  async function save() {
    const document = useEditor.getState().document();
    if (!document) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/v1/admin/waves/${encodeURIComponent(id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(document),
      });
      if (!response.ok) {
        // The engine reports every violation at a JSON Pointer. Shown verbatim rather than
        // summarised, because the pointer is the part that tells an author which field to open.
        setError(`The engine refused the document: ${await response.text()}`);
        return;
      }
      load(document);
    } finally {
      setSaving(false);
    }
  }

  if (!wave) {
    return (
      <main className="screen">
        {error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}
        <Link href={href()}>Back to the catalogue</Link>
      </main>
    );
  }

  return (
    <main className="screen" style={{ maxWidth: '72rem' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div>
          <h1 style={{ marginBottom: 0 }}>{wave.name}</h1>
          <p className="muted" style={{ marginTop: '0.25rem' }}>
            <code>{wave.id}</code> · order {wave.progression_config.order} ·{' '}
            {wave.published ? 'published' : 'draft'}
            {dirty ? ' · unsaved changes' : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link href={href()} style={{ alignSelf: 'center' }}>
            Catalogue
          </Link>
          <button type="button" onClick={() => void save()} disabled={saving || !dirty}>
            {saving ? 'Saving…' : 'Save draft'}
          </button>
        </div>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <section style={{ marginTop: '1.5rem' }}>
        <h2 style={{ fontSize: '15px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Spawn rules
        </h2>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {timelines.map((timeline, index) => (
            <button
              key={index}
              type="button"
              onClick={() => selectRule(index)}
              style={{
                background: index === selectedRule ? 'var(--blue)' : 'var(--navy-raised)',
                color: index === selectedRule ? 'var(--navy)' : 'var(--text)',
                border: '1px solid var(--slate)',
              }}
            >
              Rule {index + 1} · {timeline.length} movement{timeline.length === 1 ? '' : 's'}
            </button>
          ))}
        </div>
      </section>

      <section style={{ marginTop: '1.5rem' }}>
        <Timeline />
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
          {MOVEMENT_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => addBlock(type)}
              style={{
                background: 'var(--navy-raised)',
                color: 'var(--text)',
                border: '1px solid var(--slate)',
                fontSize: '12px',
                padding: '0.35rem 0.6rem',
              }}
            >
              + {type}
            </button>
          ))}
        </div>
      </section>

      <section
        style={{
          marginTop: '1.5rem',
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 22rem',
          gap: '1.5rem',
          alignItems: 'start',
        }}
      >
        <Preview
          wave={useEditor.getState().document() ?? wave}
          seconds={playhead}
          onScrub={setPlayhead}
        />
        <Inspector />
      </section>
    </main>
  );
}
