import { describe, expect, it } from 'vitest';
import {
  checkItemDraft,
  checkSchemaText,
  draftOf,
  emptyItemDraft,
  inventory,
  type ItemView,
} from '@/modules/inventory/api';
import { empty, json, mockEngine } from '@/test/engine';

const sword: ItemView = {
  id: 'sword',
  name: 'Sword',
  itemType: 'weapon',
  spriteRef: 'spr_1',
  attributes: '{"damage": 12}',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-02T00:00:00Z',
};

describe('the inventory calls', () => {
  it('lists the catalogue from listItems', async () => {
    const sent = mockEngine({ 'GET /api/v1/admin/items': json([sword]) });

    await expect(inventory.items()).resolves.toEqual([sword]);
    expect(sent[0]?.authorization).toBe('Bearer test-token');
  });

  it('saves with saveItem: a PUT at the id, with the contract field names', async () => {
    const sent = mockEngine({ 'PUT /api/v1/admin/items/sword': json(sword) });

    await inventory.save({
      id: 'sword',
      name: ' Sword ',
      itemType: 'weapon',
      spriteRef: 'spr_1',
      attributes: '{"damage": 12}',
    });

    expect(sent[0]?.contentType).toBe('application/json');
    expect(sent[0]?.body).toEqual({
      name: 'Sword',
      itemType: 'weapon',
      spriteRef: 'spr_1',
      // Text inside a string, as the contract has it: the engine stores the characters the author
      // wrote, so the editor must not parse and re-serialise them.
      attributes: '{"damage": 12}',
    });
  });

  it('leaves out a blank sprite and blank attributes rather than sending empty strings', async () => {
    const sent = mockEngine({ 'PUT /api/v1/admin/items/shield': json({ ...sword, id: 'shield' }) });

    await inventory.save({ id: 'shield', name: 'Shield', itemType: 'armour', spriteRef: ' ', attributes: '' });

    expect(sent[0]?.body).toEqual({ name: 'Shield', itemType: 'armour' });
  });

  it('deletes with deleteItem and accepts the 204', async () => {
    const sent = mockEngine({ 'DELETE /api/v1/admin/items/sword': empty(204) });

    await inventory.remove('sword');

    expect(sent.map((r) => `${r.method} ${r.path}`)).toEqual(['DELETE /api/v1/admin/items/sword']);
  });

  it('encodes the id into the path', async () => {
    const sent = mockEngine({ 'GET /api/v1/admin/items/a%2Fb': json(sword) });

    await inventory.item('a/b');

    expect(sent[0]?.path).toBe('/api/v1/admin/items/a%2Fb');
  });

  it('reads and replaces the schema as text, byte for byte', async () => {
    const text = '{\n  "type": "object",\n  "properties": {"damage": {"minimum": 0}}\n}';
    const sent = mockEngine({
      'GET /api/v1/admin/item-schema': new Response('{}', { status: 200 }),
      'PUT /api/v1/admin/item-schema': (request) => new Response(request.raw, { status: 200 }),
    });

    await expect(inventory.schema()).resolves.toBe('{}');
    await expect(inventory.replaceSchema(text)).resolves.toBe(text);

    const put = sent.find((r) => r.method === 'PUT');
    expect(put?.contentType).toBe('application/json');
    expect(put?.raw).toBe(text);
  });

  it("surfaces the engine's pointer when an item is refused", async () => {
    mockEngine({
      'PUT /api/v1/admin/items/sword': json({ detail: '/attributes/damage: -1 is less than 0' }, 422),
    });

    await expect(inventory.save(draftOf(sword))).rejects.toThrow('/attributes/damage');
  });
});

describe('checking an item before it is sent', () => {
  it('accepts a complete draft', () => {
    expect(checkItemDraft(draftOf(sword))).toEqual([]);
  });

  it('names each field that is wrong', () => {
    expect(
      checkItemDraft({ id: 'Big Sword', name: ' ', itemType: 'Weapon!', spriteRef: '', attributes: '[1]' }),
    ).toEqual([
      'id: lowercase letters, digits and _ only',
      'name: an item needs a name',
      'item type: lowercase letters, digits and _ only',
      'attributes: a JSON object, such as {"damage": 12}',
    ]);
  });

  it('reports attributes that are not JSON at all', () => {
    expect(checkItemDraft({ ...draftOf(sword), attributes: '{damage: 12}' })).toEqual([
      'attributes: not valid JSON',
    ]);
  });

  it('allows blank attributes, which the engine stores as {}', () => {
    expect(checkItemDraft({ ...draftOf(sword), attributes: '  ' })).toEqual([]);
  });

  it('starts a new item blank, with empty attributes', () => {
    expect(emptyItemDraft()).toEqual({ id: '', name: '', itemType: '', spriteRef: '', attributes: '{}' });
  });
});

describe('checking a schema before it is sent', () => {
  it('accepts a JSON object', () => {
    expect(checkSchemaText('{"type": "object"}')).toBeNull();
  });

  it('refuses anything else', () => {
    expect(checkSchemaText('')).toMatch(/JSON object/);
    expect(checkSchemaText('[]')).toMatch(/JSON object/);
    expect(checkSchemaText('{oops')).toMatch(/not valid JSON/);
  });
});
