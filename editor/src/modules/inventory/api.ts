import { jsonBody, segment, send, sendJson, sendText } from '@/lib/requests';

/**
 * The item catalogue and its attribute schema: `listItems`, `getItem`, `saveItem`, `deleteItem`,
 * `getItemSchema` and `replaceItemSchema` in the v1 contract.
 *
 * Attributes travel as JSON *text* inside a string, as the contract has them. The engine stores the
 * characters it was sent, so this layer never parses and re-serialises them: it would reorder keys
 * and change whitespace in a document the author wrote by hand.
 */
export type ItemView = {
  id: string;
  name: string;
  itemType: string;
  spriteRef?: string | null;
  attributes: string;
  createdAt: string;
  updatedAt: string;
};

/** An item as the form holds it: every field a string, the id included. */
export type ItemDraft = {
  id: string;
  name: string;
  itemType: string;
  spriteRef: string;
  attributes: string;
};

type ItemRequest = { name: string; itemType: string; spriteRef?: string; attributes?: string };

const ITEMS = '/api/v1/admin/items';
const SCHEMA = '/api/v1/admin/item-schema';

/** Ids and types, as the engine accepts them. */
const SLUG = /^[a-z0-9_]{1,64}$/;

function requestOf(draft: ItemDraft): ItemRequest {
  const request: ItemRequest = { name: draft.name.trim(), itemType: draft.itemType.trim() };
  const spriteRef = draft.spriteRef.trim();
  if (spriteRef) {
    request.spriteRef = spriteRef;
  }
  if (draft.attributes.trim()) {
    request.attributes = draft.attributes;
  }
  return request;
}

export const inventory = {
  items: (): Promise<ItemView[]> => sendJson<ItemView[]>(ITEMS),

  item: (id: string): Promise<ItemView> => sendJson<ItemView>(`${ITEMS}/${segment(id)}`),

  save: (draft: ItemDraft): Promise<ItemView> =>
    sendJson<ItemView>(`${ITEMS}/${segment(draft.id.trim())}`, jsonBody('PUT', requestOf(draft))),

  remove: async (id: string): Promise<void> => {
    await send(`${ITEMS}/${segment(id)}`, { method: 'DELETE' });
  },

  /** The schema as the engine stored it, or `{}` when the project has none. */
  schema: (): Promise<string> => sendText(SCHEMA),

  /** The body is the schema itself, sent as written; the answer is the text stored. */
  replaceSchema: (text: string): Promise<string> =>
    sendText(SCHEMA, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: text,
    }),
};

export function emptyItemDraft(): ItemDraft {
  return { id: '', name: '', itemType: '', spriteRef: '', attributes: '{}' };
}

export function draftOf(item: ItemView): ItemDraft {
  return {
    id: item.id,
    name: item.name,
    itemType: item.itemType,
    spriteRef: item.spriteRef ?? '',
    attributes: item.attributes,
  };
}

function jsonProblem(text: string): 'invalid' | 'not-object' | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? null
      : 'not-object';
  } catch {
    return 'invalid';
  }
}

/**
 * What is wrong with a draft, one line per field, before it is sent. The engine checks all of this
 * again, and the project's schema besides; this only saves a round trip for the obvious mistakes.
 */
export function checkItemDraft(draft: ItemDraft): string[] {
  const problems: string[] = [];
  if (!SLUG.test(draft.id.trim())) {
    problems.push('id: lowercase letters, digits and _ only');
  }
  if (!draft.name.trim()) {
    problems.push('name: an item needs a name');
  }
  if (!SLUG.test(draft.itemType.trim())) {
    problems.push('item type: lowercase letters, digits and _ only');
  }
  if (draft.attributes.trim()) {
    const problem = jsonProblem(draft.attributes);
    if (problem === 'invalid') {
      problems.push('attributes: not valid JSON');
    } else if (problem === 'not-object') {
      problems.push('attributes: a JSON object, such as {"damage": 12}');
    }
  }
  return problems;
}

/** Null when the text is a schema the engine could consider, otherwise why not. */
export function checkSchemaText(text: string): string | null {
  const problem = jsonProblem(text);
  if (problem === 'invalid') {
    return text.trim() ? 'The schema is not valid JSON.' : 'The schema is a JSON object; use {} for none.';
  }
  if (problem === 'not-object') {
    return 'The schema is a JSON object; use {} for none.';
  }
  return null;
}
