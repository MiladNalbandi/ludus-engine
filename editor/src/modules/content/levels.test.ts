import { describe, expect, it } from 'vitest';
import {
  addWave,
  checkLevel,
  draftOfLevel,
  levelRequest,
  levels,
  moveWave,
  removeWaveAt,
} from '@/modules/content/levels';
import type { WaveLevelSummary } from '@/modules/content/waves';
import { empty, json, mockEngine } from '@/test/engine';

const level: WaveLevelSummary = {
  id: 'lvl_1',
  name: 'Opening',
  description: null,
  active: false,
  waves: [
    { waveId: 'w1', published: true },
    { waveId: 'w2', published: false },
  ],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('the level calls', () => {
  it('creates a level with createWaveLevel, waves in play order', async () => {
    const sent = mockEngine({ 'POST /api/v1/admin/wave-levels': json(level, 201) });

    await expect(
      levels.create({ name: ' Opening ', description: '', waves: ['w1', 'w2'] }),
    ).resolves.toEqual(level);
    expect(sent[0]?.body).toEqual({ name: 'Opening', waves: ['w1', 'w2'] });
    expect(sent[0]?.contentType).toBe('application/json');
  });

  it('reads one level with getWaveLevel', async () => {
    mockEngine({ 'GET /api/v1/admin/wave-levels/lvl_1': json(level) });

    await expect(levels.get('lvl_1')).resolves.toEqual(level);
  });

  it('replaces the name, description and wave list with updateWaveLevel', async () => {
    const sent = mockEngine({ 'PUT /api/v1/admin/wave-levels/lvl_1': json(level) });

    await levels.update('lvl_1', { name: 'Opening', description: ' Two waves ', waves: ['w2', 'w1'] });

    expect(sent[0]?.body).toEqual({ name: 'Opening', description: 'Two waves', waves: ['w2', 'w1'] });
  });

  it('deletes with deleteWaveLevel and accepts the 204', async () => {
    const sent = mockEngine({ 'DELETE /api/v1/admin/wave-levels/lvl_1': empty() });

    await levels.remove('lvl_1');

    expect(sent[0]?.method).toBe('DELETE');
  });

  it("surfaces the engine's pointer when a level is refused", async () => {
    mockEngine({
      'POST /api/v1/admin/wave-levels': json({ detail: '/waves/1: w9 is not a wave.' }, 422),
    });

    await expect(levels.create({ name: 'x', description: '', waves: ['w1', 'w9'] })).rejects.toThrow(
      '/waves/1',
    );
  });
});

describe('editing the wave order', () => {
  it('starts from the level as stored', () => {
    expect(draftOfLevel(level)).toEqual({ name: 'Opening', description: '', waves: ['w1', 'w2'] });
  });

  it('moves a wave up and down', () => {
    expect(moveWave(['a', 'b', 'c'], 2, -1)).toEqual(['a', 'c', 'b']);
    expect(moveWave(['a', 'b', 'c'], 0, 1)).toEqual(['b', 'a', 'c']);
  });

  it('does nothing past either end', () => {
    expect(moveWave(['a', 'b'], 0, -1)).toEqual(['a', 'b']);
    expect(moveWave(['a', 'b'], 1, 1)).toEqual(['a', 'b']);
  });

  it('removes one wave by position', () => {
    expect(removeWaveAt(['a', 'b', 'c'], 1)).toEqual(['a', 'c']);
  });

  it('adds a wave at the end, and refuses one already in the level', () => {
    // The engine refuses a level that names a wave twice; refusing here keeps the button honest.
    expect(addWave(['a'], 'b')).toEqual(['a', 'b']);
    expect(addWave(['a', 'b'], 'a')).toEqual(['a', 'b']);
  });

  it('never changes the list it was given', () => {
    const waves = ['a', 'b'];
    moveWave(waves, 0, 1);
    removeWaveAt(waves, 0);
    addWave(waves, 'c');

    expect(waves).toEqual(['a', 'b']);
  });
});

describe('checking a level before it is sent', () => {
  it('needs a name', () => {
    expect(checkLevel({ name: ' ', description: '', waves: [] })).toEqual(['name: a level needs a name']);
  });

  it('allows a level with no waves yet, as the engine does', () => {
    expect(checkLevel({ name: 'Empty', description: '', waves: [] })).toEqual([]);
  });

  it('builds the request with the contract field names', () => {
    expect(levelRequest({ name: 'A', description: 'B', waves: ['w1'] })).toEqual({
      name: 'A',
      description: 'B',
      waves: ['w1'],
    });
  });
});
