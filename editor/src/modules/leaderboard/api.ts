import { jsonBody, segment, send, sendJson } from '@/lib/requests';

/**
 * Boards and their pages: `listLeaderboardsAsAdmin`, `getLeaderboardPageAsAdmin`,
 * `saveLeaderboard` and `deleteLeaderboard` in the v1 contract.
 *
 * The admin page takes only `limit` in the contract, so this layer reads the first page of a board
 * at a chosen size and does not follow `nextCursor`: a cursor the contract does not name is a
 * parameter the Java engine never accepted.
 */
export type LeaderboardView = {
  id: string;
  name: string;
  descending: boolean;
  createdAt: string;
  updatedAt: string;
};

export type LeaderboardEntryView = {
  playerId: string;
  displayName: string;
  score: number;
  rank: number;
  updatedAt: string;
};

export type LeaderboardPage = {
  board: LeaderboardView;
  entries: LeaderboardEntryView[];
  total: number;
  nextCursor?: string | null;
};

export type BoardRequest = { name: string; descending: boolean };

const BOARDS = '/api/v1/admin/leaderboards';

/** As the engine accepts them. */
const BOARD_ID = /^[a-z0-9_]{1,64}$/;

export const leaderboards = {
  list: (): Promise<LeaderboardView[]> => sendJson<LeaderboardView[]>(BOARDS),

  page: (boardId: string, limit = 50): Promise<LeaderboardPage> =>
    sendJson<LeaderboardPage>(
      `${BOARDS}/${segment(boardId)}?${new URLSearchParams({ limit: String(limit) }).toString()}`,
    ),

  save: (boardId: string, board: BoardRequest): Promise<LeaderboardView> =>
    sendJson<LeaderboardView>(
      `${BOARDS}/${segment(boardId)}`,
      jsonBody('PUT', { name: board.name.trim(), descending: board.descending }),
    ),

  remove: async (boardId: string): Promise<void> => {
    await send(`${BOARDS}/${segment(boardId)}`, { method: 'DELETE' });
  },
};

export function checkBoard(id: string, name: string): string[] {
  const problems: string[] = [];
  if (!BOARD_ID.test(id.trim())) {
    problems.push('id: lowercase letters, digits and _ only');
  }
  if (!name.trim()) {
    problems.push('name: a board needs a name');
  }
  return problems;
}
