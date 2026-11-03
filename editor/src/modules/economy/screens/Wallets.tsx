'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import type { ModuleScreenProps } from '@/shell/module';
import { formatMoment, useEngineCall } from '@/lib/useEngineCall';
import { EngineError, Problems } from '@/lib/ui';
import {
  checkGrant,
  economy,
  withBalance,
  type PlayerProfile,
  type PlayerWallet,
} from '@/modules/economy/api';

/**
 * Players on the left, one player's wallet on the right, and the one write this screen offers:
 * granting currency. Spending belongs to the game client, under the player's own token.
 */
export default function WalletsScreen({ params, href }: ModuleScreenProps) {
  const selected = params.id;
  const list = useEngineCall();
  const detail = useEngineCall();
  const [players, setPlayers] = useState<PlayerProfile[] | null>(null);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [wallet, setWallet] = useState<PlayerWallet | null>(null);
  const [currency, setCurrency] = useState('');
  const [amount, setAmount] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [granted, setGranted] = useState<string | null>(null);

  const runList = list.run;
  const runDetail = detail.run;

  const loadPlayers = useCallback(
    async (after?: string) => {
      const page = await runList(() => economy.players(after));
      if (!page) {
        return;
      }
      setPlayers((existing) => (after && existing ? [...existing, ...page.players] : page.players));
      setTotal(page.total);
      setCursor(page.nextCursor ?? null);
    },
    [runList],
  );

  useEffect(() => {
    void loadPlayers();
  }, [loadPlayers]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    void (async () => {
      const found = await runDetail(() => economy.wallet(selected));
      if (found) {
        setWallet(found);
      }
    })();
  }, [runDetail, selected]);

  const player = players?.find((candidate) => candidate.id === selected) ?? null;
  const name = player?.displayName || player?.externalId || 'this player';

  async function grant() {
    if (!selected) {
      return;
    }
    const check = checkGrant(currency, amount);
    if (!check.ok) {
      setProblem(check.problem);
      return;
    }
    setProblem(null);
    const balance = await runDetail(() => economy.grant(selected, check.grant));
    if (balance) {
      setWallet((current) => withBalance(current ?? { balances: [] }, balance));
      setGranted(`Granted ${check.grant.amount} ${check.grant.currency} to ${name}.`);
      setAmount('');
    }
  }

  return (
    <main className="screen" style={{ maxWidth: '68rem' }}>
      <header className="screen-header">
        <div>
          <h1>Wallets</h1>
          <p className="screen-lede">
            What each player holds. Grant currency here; players spend it from the game.
          </p>
        </div>
      </header>

      <div className="split">
        <section aria-labelledby="players-title">
          <h2 id="players-title" style={{ fontSize: '17px' }}>
            {players ? `${total} player${total === 1 ? '' : 's'}` : 'Players'}
          </h2>
          <EngineError message={list.error} />
          {players === null ? (
            list.error ? null : <p className="muted">Loading…</p>
          ) : players.length === 0 ? (
            <p className="muted">
              No players yet. A player appears here after their first session from the game.
            </p>
          ) : (
            <>
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Player</th>
                      <th scope="col">External id</th>
                      <th scope="col">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {players.map((entry) => (
                      <tr key={entry.id} className={entry.id === selected ? 'selected' : undefined}>
                        <td>
                          <Link
                            href={href('players', entry.id)}
                            aria-current={entry.id === selected ? 'page' : undefined}
                          >
                            {entry.displayName || entry.externalId}
                          </Link>
                        </td>
                        <td className="muted">
                          <code>{entry.externalId}</code>
                        </td>
                        <td className="muted">{formatMoment(entry.lastSeenAt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {cursor ? (
                <button
                  type="button"
                  className="quiet"
                  style={{ marginTop: '1rem' }}
                  disabled={list.busy}
                  onClick={() => void loadPlayers(cursor)}
                >
                  {list.busy ? 'Loading…' : 'Show more players'}
                </button>
              ) : null}
            </>
          )}
        </section>

        <section className="panel" aria-labelledby="wallet-title">
          {!selected ? (
            <>
              <h2 id="wallet-title">Wallet</h2>
              <p className="muted" style={{ margin: 0 }}>
                Choose a player to see their balances and grant currency.
              </p>
            </>
          ) : (
            <>
              <h2 id="wallet-title">{player ? `${name}'s wallet` : 'Wallet'}</h2>
              {wallet === null ? (
                detail.error ? null : <p className="muted">Loading…</p>
              ) : wallet.balances.length === 0 ? (
                <p className="muted">No currency yet.</p>
              ) : (
                <table className="data" style={{ marginBottom: '1.25rem' }}>
                  <thead>
                    <tr>
                      <th scope="col">Currency</th>
                      <th scope="col" className="number">
                        Amount
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {wallet.balances.map((balance) => (
                      <tr key={balance.currency}>
                        <td>{balance.currency}</td>
                        <td className="number">{balance.amount.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <form
                className="form-stack"
                onSubmit={(event) => {
                  event.preventDefault();
                  void grant();
                }}
              >
                <div>
                  <label htmlFor="grant-currency">Currency</label>
                  <input
                    id="grant-currency"
                    list="grant-currencies"
                    value={currency}
                    placeholder="coins"
                    onChange={(event) => setCurrency(event.target.value)}
                  />
                  <datalist id="grant-currencies">
                    {wallet?.balances.map((balance) => (
                      <option key={balance.currency} value={balance.currency} />
                    ))}
                  </datalist>
                </div>
                <div>
                  <label htmlFor="grant-amount">Amount</label>
                  <input
                    id="grant-amount"
                    inputMode="numeric"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                  />
                </div>
                <Problems problems={problem ? [problem] : []} />
                <EngineError message={detail.error} />
                <div className="actions">
                  <button type="submit" disabled={detail.busy}>
                    {detail.busy ? 'Granting…' : 'Grant currency'}
                  </button>
                  {granted ? (
                    <span className="notice" role="status">
                      {granted}
                    </span>
                  ) : null}
                </div>
              </form>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
