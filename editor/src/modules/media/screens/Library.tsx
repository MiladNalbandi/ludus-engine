'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ModuleScreenProps } from '@/shell/module';
import { formatMoment, useEngineCall } from '@/lib/useEngineCall';
import { ConfirmDelete, EngineError, SubNav } from '@/lib/ui';
import { formatBytes, media, type MediaKind, type MediaSummary } from '@/modules/media/api';

/**
 * One media library — audio clips or sprites — as a list with an upload form above it.
 *
 * The engine decides what it accepts from the bytes, not the file name, so `accept` here only
 * narrows the file picker. A refusal (an SVG sprite, a file too large) comes back in the engine's
 * own words.
 */
type Library = {
  kind: MediaKind;
  title: string;
  lede: string;
  noun: string;
  accept: string;
  tab: 'audio' | 'sprites';
  preview: (item: MediaSummary, url: string) => React.ReactNode;
};

function LibraryScreen({ href, library }: ModuleScreenProps & { library: Library }) {
  const { kind } = library;
  const { error, busy, run } = useEngineCall();
  const [items, setItems] = useState<MediaSummary[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const list = await run(() => kind.list());
    if (list) {
      setItems(list);
    }
  }, [kind, run]);

  useEffect(() => {
    void load();
  }, [load]);

  async function upload() {
    if (!file) {
      return;
    }
    const uploaded = await run(() => kind.upload(file));
    if (uploaded) {
      setNotice(`Uploaded ${uploaded.filename}.`);
      setFile(null);
      if (picker.current) {
        picker.current.value = '';
      }
      await load();
    }
  }

  async function remove(item: MediaSummary) {
    const done = await run(async () => {
      await kind.remove(item.id);
      return true;
    });
    if (done) {
      setNotice(`Deleted ${item.filename}.`);
      await load();
    }
  }

  return (
    <main className="screen" style={{ maxWidth: '64rem' }}>
      <header className="screen-header">
        <div>
          <h1>{library.title}</h1>
          <p className="screen-lede">{library.lede}</p>
        </div>
      </header>
      <SubNav
        label="Media"
        tabs={[
          { href: href(), label: 'Audio clips', current: library.tab === 'audio' },
          { href: href('sprites'), label: 'Sprites', current: library.tab === 'sprites' },
        ]}
      />

      <form
        className="panel media-upload"
        onSubmit={(event) => {
          event.preventDefault();
          void upload();
        }}
      >
        <div style={{ flex: 1, minWidth: '14rem' }}>
          <label htmlFor="media-file">Choose a {library.noun} to upload</label>
          <input
            ref={picker}
            id="media-file"
            type="file"
            accept={library.accept}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setNotice(null);
            }}
          />
        </div>
        <button type="submit" disabled={!file || busy}>
          {busy && file ? 'Uploading…' : 'Upload'}
        </button>
      </form>

      <EngineError message={error} />
      {notice ? (
        <p className="notice" role="status">
          {notice}
        </p>
      ) : null}

      <section aria-labelledby="media-list-title" style={{ marginTop: '1.5rem' }}>
        <h2 id="media-list-title" style={{ fontSize: '17px' }}>
          {items ? `${items.length} ${library.noun}${items.length === 1 ? '' : 's'}` : library.title}
        </h2>
        {items === null ? (
          error ? null : <p className="muted">Loading…</p>
        ) : items.length === 0 ? (
          <p className="muted">Nothing uploaded yet. Choose a file above to add the first.</p>
        ) : (
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Preview</th>
                  <th scope="col">File</th>
                  <th scope="col">Type</th>
                  <th scope="col" className="number">
                    Size
                  </th>
                  <th scope="col">Uploaded</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{library.preview(item, kind.url(item.id))}</td>
                    <td>
                      {item.filename}
                      <br />
                      <code className="muted" style={{ fontSize: '12px' }}>
                        {item.id}
                      </code>
                    </td>
                    <td className="muted">{item.contentType}</td>
                    <td className="number">{formatBytes(item.sizeBytes)}</td>
                    <td className="muted">{formatMoment(item.createdAt)}</td>
                    <td>
                      <ConfirmDelete what={item.filename} onConfirm={() => void remove(item)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

const AUDIO: Library = {
  kind: media.audio,
  title: 'Audio clips',
  lede: 'Sound the game streams from the engine. Each clip plays here from the same public address a client uses.',
  noun: 'clip',
  accept: 'audio/*',
  tab: 'audio',
  preview: (item, url) => (
    <audio controls preload="none" src={url} aria-label={`Play ${item.filename}`} style={{ height: '2rem', maxWidth: '14rem' }} />
  ),
};

const SPRITES: Library = {
  kind: media.sprites,
  title: 'Sprites',
  lede: 'Images for items and entities. SVG is refused: the engine checks the bytes, not the name.',
  noun: 'sprite',
  accept: 'image/png,image/jpeg,image/gif,image/webp',
  tab: 'sprites',
  preview: (item, url) => (
    // eslint-disable-next-line @next/next/no-img-element -- streamed from the engine, not optimisable
    <img src={url} alt={item.filename} className="sprite-thumb" loading="lazy" />
  ),
};

export function AudioScreen(props: ModuleScreenProps) {
  return <LibraryScreen {...props} library={AUDIO} />;
}

export function SpritesScreen(props: ModuleScreenProps) {
  return <LibraryScreen {...props} library={SPRITES} />;
}
