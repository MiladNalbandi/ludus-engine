'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ModuleScreenProps } from '@/shell/module';
import { useEngineCall } from '@/lib/useEngineCall';
import { ConfirmDelete, EngineError, Problems } from '@/lib/ui';
import {
  checkBoard,
  leaderboards,
  type LeaderboardPage,
  type LeaderboardView,
} from '@/modules/leaderboard/api';

/**
 * The project's boards, one board's standings, and the form that creates or changes a board.
 *
 * Which way a board sorts belongs to the board, so changing it re-ranks every entry at once; the
 * form says so in words rather than as a bare "descending" switch.
 */
const PAGE_SIZES = [10, 25, 50, 100];

type BoardForm = { id: string; name: string; higherWins: boolean };

const BLANK: BoardForm = { id: '', name: '', higherWins: true };

export default function BoardsScreen({ params, href }: ModuleScreenProps) {
  const router = useRouter();
  const selected = params.id;
  const list = useEngineCall();
  const standing = useEngineCall();
  const [boards, setBoards] = useState<LeaderboardView[] | null>(null);
  const [page, setPage] = useState<LeaderboardPage | null>(null);
  const [size, setSize] = useState(25);
  const [form, setForm] = useState<BoardForm>(BLANK);
  const [problems, setProblems] = useState<string[]>([]);
  const [saved, setSaved] = useState<string | null>(null);

  const runList = list.run;
  const runStanding = standing.run;

  const loadBoards = useCallback(async () => {
    const found = await runList(() => leaderboards.list());
    if (!found) {
      return;
    }
    setBoards(found);
    const current = selected ? found.find((board) => board.id === selected) : undefined;
    setForm(
      current ? { id: current.id, name: current.name, higherWins: current.descending } : BLANK,
    );
  }, [runList, selected]);

  useEffect(() => {
    void loadBoards();
  }, [loadBoards]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    void (async () => {
      const found = await runStanding(() => leaderboards.page(selected, size));
      if (found) {
        setPage(found);
      }
    })();
  }, [runStanding, selected, size]);

  const board = selected ? (boards?.find((candidate) => candidate.id === selected) ?? null) : null;

  async function save() {
    const found = checkBoard(form.id, form.name);
    setProblems(found);
    if (found.length > 0) {
      return;
    }
    const id = form.id.trim();
    const result = await runList(() =>
      leaderboards.save(id, { name: form.name, descending: form.higherWins }),
    );
    if (!result) {
      return;
    }
    setSaved(`Saved ${result.name}.`);
    if (id !== selected) {
      router.push(href('boards', id));
      return;
    }
    await loadBoards();
    const refreshed = await runStanding(() => leaderboards.page(id, size));
    if (refreshed) {
      setPage(refreshed);
    }
  }

  async function remove(id: string) {
    const done = await runList(async () => {
      await leaderboards.remove(id);
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
          <h1>Leaderboards</h1>
          <p className="screen-lede">
            Boards the game submits scores to. Players post their own scores from the game; this is
            where a board is defined and its standings read.
          </p>
        </div>
      </header>

      <div className="split">
        <div>
          <section aria-labelledby="boards-title">
            <h2 id="boards-title" style={{ fontSize: '17px' }}>
              Boards
            </h2>
            {boards === null ? (
              list.error ? null : <p className="muted">Loading…</p>
            ) : boards.length === 0 ? (
              <p className="muted">No boards yet. Create the first with the form.</p>
            ) : (
              <ul className="board-list">
                {boards.map((entry) => (
                  <li key={entry.id}>
                    <Link
                      href={href('boards', entry.id)}
                      aria-current={entry.id === selected ? 'page' : undefined}
                    >
                      {entry.name}
                    </Link>
                    <span className="muted">
                      <code>{entry.id}</code>, {entry.descending ? 'higher wins' : 'lower wins'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {selected ? (
            <section aria-labelledby="standings-title" style={{ marginTop: '2rem' }}>
              <div className="screen-header">
                <h2 id="standings-title" style={{ fontSize: '17px', margin: 0 }}>
                  {board ? `${board.name} standings` : 'Standings'}
                </h2>
                <div className="actions">
                  <label htmlFor="standings-size" style={{ margin: 0 }}>
                    Rows
                  </label>
                  <select
                    id="standings-size"
                    value={size}
                    style={{ width: 'auto' }}
                    onChange={(event) => setSize(Number(event.target.value))}
                  >
                    {PAGE_SIZES.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <EngineError message={standing.error} />
              {page === null ? (
                standing.error ? null : <p className="muted">Loading…</p>
              ) : page.entries.length === 0 ? (
                <p className="muted">No scores yet.</p>
              ) : (
                <>
                  <p className="notice">
                    Showing the top {page.entries.length} of {page.total}.
                  </p>
                  <div className="table-scroll">
                    <table className="data">
                      <thead>
                        <tr>
                          <th scope="col" className="number">
                            Rank
                          </th>
                          <th scope="col">Player</th>
                          <th scope="col" className="number">
                            Score
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {page.entries.map((entry) => (
                          <tr key={entry.playerId}>
                            <td className="number">{entry.rank}</td>
                            <td>
                              {entry.displayName || (
                                <code className="muted" style={{ fontSize: '12px' }}>
                                  {entry.playerId}
                                </code>
                              )}
                            </td>
                            <td className="number">{entry.score.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </section>
          ) : null}
        </div>

        <section className="panel" aria-labelledby="board-form-title">
          <h2 id="board-form-title">{board ? `Edit ${board.name}` : 'New board'}</h2>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <div>
              <label htmlFor="board-id">Id</label>
              <input
                id="board-id"
                value={form.id}
                readOnly={board !== null}
                placeholder="weekly_high_score"
                onChange={(event) => setForm({ ...form, id: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="board-name">Name</label>
              <input
                id="board-name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </div>
            <label className="check" htmlFor="board-higher-wins">
              <input
                id="board-higher-wins"
                type="checkbox"
                checked={form.higherWins}
                onChange={(event) => setForm({ ...form, higherWins: event.target.checked })}
              />
              A higher score ranks first
            </label>
            <Problems problems={problems} />
            <EngineError message={list.error} />
            <div className="actions" style={{ justifyContent: 'space-between' }}>
              <span className="actions">
                <button type="submit" disabled={list.busy}>
                  {list.busy ? 'Saving…' : 'Save board'}
                </button>
                {saved ? (
                  <span className="notice" role="status">
                    {saved}
                  </span>
                ) : null}
              </span>
              {board ? (
                <ConfirmDelete what={board.name} onConfirm={() => void remove(board.id)} />
              ) : null}
            </div>
            {board ? (
              <p className="notice" style={{ margin: 0 }}>
                Deleting a board deletes its scores with it. <Link href={href()}>New board</Link>
              </p>
            ) : null}
          </form>
        </section>
      </div>
    </main>
  );
}
