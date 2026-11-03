import { describe, expect, it } from 'vitest';
import { checkBoard, leaderboards } from '@/modules/leaderboard/api';
import { empty, json, mockEngine } from '@/test/engine';

const board = {
  id: 'weekly',
  name: 'Weekly high score',
  descending: true,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('the leaderboard calls', () => {
  it('lists boards with listLeaderboardsAsAdmin', async () => {
    mockEngine({ 'GET /api/v1/admin/leaderboards': json([board]) });

    await expect(leaderboards.list()).resolves.toEqual([board]);
  });

  it('reads a page with getLeaderboardPageAsAdmin, sending only the limit the contract names', async () => {
    const page = {
      board,
      entries: [{ playerId: 'p1', displayName: 'Ada', score: 900, rank: 1, updatedAt: 'x' }],
      total: 1,
    };
    const sent = mockEngine({ 'GET /api/v1/admin/leaderboards/weekly': json(page) });

    await expect(leaderboards.page('weekly', 50)).resolves.toEqual(page);
    expect([...(sent[0]?.query.keys() ?? [])]).toEqual(['limit']);
    expect(sent[0]?.query.get('limit')).toBe('50');
  });

  it('creates or replaces a board with saveLeaderboard: name and descending', async () => {
    const sent = mockEngine({ 'PUT /api/v1/admin/leaderboards/weekly': json(board) });

    await leaderboards.save('weekly', { name: ' Weekly high score ', descending: false });

    expect(sent[0]?.body).toEqual({ name: 'Weekly high score', descending: false });
  });

  it('deletes with deleteLeaderboard and accepts the 204', async () => {
    const sent = mockEngine({ 'DELETE /api/v1/admin/leaderboards/weekly': empty() });

    await leaderboards.remove('weekly');

    expect(sent[0]?.method).toBe('DELETE');
  });

  it('says plainly when a board is not there', async () => {
    mockEngine({ 'GET /api/v1/admin/leaderboards/gone': json({ detail: "There is no board 'gone'." }, 404) });

    await expect(leaderboards.page('gone')).rejects.toThrow("There is no board 'gone'.");
  });
});

describe('checking a board before it is sent', () => {
  it('accepts an id and a name', () => {
    expect(checkBoard('weekly_2', 'Weekly')).toEqual([]);
  });

  it('refuses a hyphen, which the engine does not accept in a board id', () => {
    expect(checkBoard('weekly-2', 'Weekly')).toHaveLength(1);
  });

  it('names what is wrong', () => {
    expect(checkBoard('Weekly Board', '  ')).toEqual([
      'id: lowercase letters, digits and _ only',
      'name: a board needs a name',
    ]);
  });
});
