import { describe, expect, it } from 'vitest';
import { Refused, send, sendJson, sendText } from '@/lib/requests';
import { empty, json, mockEngine } from '@/test/engine';

/**
 * The one way module screens talk to the engine: through `apiFetch`, with a refusal turned into an
 * error that carries what the engine said.
 *
 * The engine's message is the useful part of a refusal. A validation failure names the JSON
 * Pointer of the field that is wrong, and a screen that reported "422" instead would leave an
 * author guessing which of their fields to open.
 */
describe('send', () => {
  it('resolves on any 2xx, including a 204 with no body', async () => {
    mockEngine({ 'DELETE /api/v1/admin/items/sword': empty(204) });

    await expect(send('/api/v1/admin/items/sword', { method: 'DELETE' })).resolves.toBeInstanceOf(
      Response,
    );
  });

  it("carries a FastAPI service's detail", async () => {
    mockEngine({ 'GET /x': json({ detail: '/attributes/damage: -1 is less than 0' }, 422) });

    const refused = await send('/x').catch((thrown: unknown) => thrown);

    expect(refused).toBeInstanceOf(Refused);
    expect((refused as Refused).status).toBe(422);
    expect((refused as Refused).message).toBe('/attributes/damage: -1 is less than 0');
  });

  it('joins a list of validation errors into one message', async () => {
    mockEngine({
      'GET /x': json(
        { detail: [{ loc: ['body', 'amount'], msg: 'must be a whole number' }, { msg: 'and more' }] },
        422,
      ),
    });

    await expect(send('/x')).rejects.toThrow('body.amount: must be a whole number; and more');
  });

  it('falls back to a problem document, then to the text, then to the status', async () => {
    mockEngine({ 'GET /a': json({ title: 'Conflict', detail: null }, 409) });
    await expect(send('/a')).rejects.toThrow('Conflict');

    mockEngine({ 'GET /b': new Response('plain words', { status: 400 }) });
    await expect(send('/b')).rejects.toThrow('plain words');

    mockEngine({ 'GET /c': new Response(null, { status: 500 }) });
    await expect(send('/c')).rejects.toThrow('GET /c failed: 500');
  });
});

describe('sendJson and sendText', () => {
  it('decodes JSON', async () => {
    mockEngine({ 'GET /x': json({ a: 1 }) });

    await expect(sendJson<{ a: number }>('/x')).resolves.toEqual({ a: 1 });
  });

  it('returns text exactly as the engine sent it', async () => {
    mockEngine({ 'GET /x': new Response('{ "type" :"object" }', { status: 200 }) });

    await expect(sendText('/x')).resolves.toBe('{ "type" :"object" }');
  });
});
