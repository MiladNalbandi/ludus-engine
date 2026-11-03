'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ModuleScreenProps } from '@/shell/module';
import { useEngineCall } from '@/lib/useEngineCall';
import { ConfirmDelete, EngineError, Problems } from '@/lib/ui';
import {
  checkItemDraft,
  draftOf,
  emptyItemDraft,
  inventory,
  type ItemDraft,
  type ItemView,
} from '@/modules/inventory/api';
import { InventoryTabs } from '@/modules/inventory/screens/InventoryTabs';

/**
 * The item catalogue: every item on the left, one item's form on the right.
 *
 * The selected item is in the address (`items/<id>`), so it survives a reload and Back returns to
 * the previous one. With no item selected the form creates a new one.
 */
export default function ItemsScreen({ params, href }: ModuleScreenProps) {
  const router = useRouter();
  const selected = params.id;
  const { error, busy, run } = useEngineCall();
  const [items, setItems] = useState<ItemView[] | null>(null);
  const [draft, setDraft] = useState<ItemDraft>(emptyItemDraft);
  const [problems, setProblems] = useState<string[]>([]);
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(async () => {
    const list = await run(() => inventory.items());
    if (!list) {
      return;
    }
    setItems(list);
    const current = selected ? list.find((item) => item.id === selected) : undefined;
    setDraft(current ? draftOf(current) : emptyItemDraft());
  }, [run, selected]);

  useEffect(() => {
    void load();
  }, [load]);

  const editing = selected ? (items?.find((item) => item.id === selected) ?? null) : null;

  async function save() {
    const found = checkItemDraft(draft);
    setProblems(found);
    if (found.length > 0) {
      return;
    }
    const item = await run(() => inventory.save(draft));
    if (!item) {
      return;
    }
    setSaved(`Saved ${item.name}.`);
    if (item.id !== selected) {
      router.push(href('items', item.id));
      return;
    }
    await load();
  }

  async function remove(id: string) {
    const done = await run(async () => {
      await inventory.remove(id);
      return true;
    });
    if (done) {
      router.push(href());
    }
  }

  return (
    <main className="screen" style={{ maxWidth: '68rem' }}>
      <header className="screen-header">
        <div>
          <h1>Items</h1>
          <p className="screen-lede">
            What players can hold. Attributes are checked against the project&apos;s attribute
            schema when an item is saved.
          </p>
        </div>
      </header>
      <InventoryTabs href={href} current="items" />

      <div className="split">
        <section aria-labelledby="items-list-title">
          <h2 id="items-list-title" style={{ fontSize: '17px' }}>
            {items ? `${items.length} item${items.length === 1 ? '' : 's'}` : 'Items'}
          </h2>
          {items === null ? (
            <p className="muted">Loading…</p>
          ) : items.length === 0 ? (
            <p className="muted">No items yet. Define the first one with the form.</p>
          ) : (
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Id</th>
                    <th scope="col">Name</th>
                    <th scope="col">Type</th>
                    <th scope="col">Sprite</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} className={item.id === selected ? 'selected' : undefined}>
                      <td>
                        <Link
                          href={href('items', item.id)}
                          aria-current={item.id === selected ? 'page' : undefined}
                        >
                          <code>{item.id}</code>
                        </Link>
                      </td>
                      <td>{item.name}</td>
                      <td className="muted">{item.itemType}</td>
                      <td className="muted">{item.spriteRef ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel" aria-labelledby="item-form-title">
          <h2 id="item-form-title">{editing ? `Edit ${editing.name}` : 'New item'}</h2>
          {selected && items && !editing ? (
            <p className="error">There is no item {selected}. It may have been deleted.</p>
          ) : null}
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <div>
              <label htmlFor="item-id">Id</label>
              <input
                id="item-id"
                value={draft.id}
                readOnly={editing !== null}
                aria-describedby="item-id-hint"
                onChange={(event) => setDraft({ ...draft, id: event.target.value })}
              />
              <p id="item-id-hint" className="notice" style={{ margin: '0.3rem 0 0' }}>
                {editing ? 'An id cannot change once an item exists.' : 'For example iron_sword.'}
              </p>
            </div>
            <div>
              <label htmlFor="item-name">Name</label>
              <input
                id="item-name"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="item-type">Item type</label>
              <input
                id="item-type"
                value={draft.itemType}
                placeholder="weapon"
                onChange={(event) => setDraft({ ...draft, itemType: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="item-sprite">Sprite</label>
              <input
                id="item-sprite"
                value={draft.spriteRef}
                placeholder="Optional sprite id"
                onChange={(event) => setDraft({ ...draft, spriteRef: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="item-attributes">Attributes</label>
              <textarea
                id="item-attributes"
                rows={7}
                spellCheck={false}
                value={draft.attributes}
                onChange={(event) => setDraft({ ...draft, attributes: event.target.value })}
              />
            </div>
            <Problems problems={problems} />
            <EngineError message={error} />
            <div className="actions" style={{ justifyContent: 'space-between' }}>
              <span className="actions">
                <button type="submit" disabled={busy}>
                  {busy ? 'Saving…' : 'Save item'}
                </button>
                {saved ? (
                  <span className="notice" role="status">
                    {saved}
                  </span>
                ) : null}
              </span>
              {editing ? (
                <ConfirmDelete what={editing.name} onConfirm={() => void remove(editing.id)} />
              ) : null}
            </div>
            {editing ? (
              <p className="notice" style={{ margin: 0 }}>
                Deleting an item also takes it out of every player&apos;s inventory.{' '}
                <Link href={href()}>Start a new item instead</Link>
              </p>
            ) : null}
          </form>
        </section>
      </div>
    </main>
  );
}
