'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ModuleScreenProps } from '@/shell/module';
import { useEngineCall } from '@/lib/useEngineCall';
import { EngineError, Problems } from '@/lib/ui';
import { checkSchemaText, inventory } from '@/modules/inventory/api';
import { InventoryTabs } from '@/modules/inventory/screens/InventoryTabs';

/**
 * The project's JSON Schema for item attributes, edited as the text it is stored as.
 *
 * Not reformatted on load or on save: the engine keeps the characters it was sent, and an editor
 * that pretty-printed them would change a document nobody asked it to change.
 */
export default function SchemaScreen({ href }: ModuleScreenProps) {
  const { error, busy, run } = useEngineCall();
  const [text, setText] = useState<string | null>(null);
  const [stored, setStored] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const schema = await run(() => inventory.schema());
    if (schema !== undefined) {
      setText(schema);
      setStored(schema);
    }
  }, [run]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (text === null) {
      return;
    }
    const found = checkSchemaText(text);
    setProblem(found);
    if (found) {
      return;
    }
    const result = await run(() => inventory.replaceSchema(text));
    if (result !== undefined) {
      setText(result);
      setStored(result);
      setSaved(true);
    }
  }

  const dirty = text !== null && text !== stored;

  return (
    <main className="screen" style={{ maxWidth: '52rem' }}>
      <header className="screen-header">
        <div>
          <h1>Attribute schema</h1>
          <p className="screen-lede">
            A JSON Schema every item&apos;s attributes must satisfy. Use {'{}'} for none. Items
            saved before a change are not checked again.
          </p>
        </div>
      </header>
      <InventoryTabs href={href} current="schema" />

      {text === null ? (
        <>
          <EngineError message={error} />
          {error ? null : <p className="muted">Loading…</p>}
        </>
      ) : (
        <form
          className="form-stack"
          style={{ marginTop: '1.5rem' }}
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div>
            <label htmlFor="item-schema">Schema</label>
            <textarea
              id="item-schema"
              rows={18}
              spellCheck={false}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                setSaved(false);
              }}
            />
          </div>
          <Problems problems={problem ? [problem] : []} />
          <EngineError message={error} />
          <div className="actions">
            <button type="submit" disabled={busy || !dirty}>
              {busy ? 'Saving…' : 'Save schema'}
            </button>
            {dirty ? (
              <button
                type="button"
                className="quiet"
                onClick={() => {
                  setText(stored);
                  setProblem(null);
                }}
              >
                Discard changes
              </button>
            ) : null}
            {saved && !dirty ? (
              <span className="notice" role="status">
                Saved. New and changed items are checked against it from now on.
              </span>
            ) : null}
          </div>
        </form>
      )}
    </main>
  );
}
