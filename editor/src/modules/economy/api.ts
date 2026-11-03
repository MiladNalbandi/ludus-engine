import { jsonBody, segment, sendJson } from '@/lib/requests';

/**
 * Players and their wallets: `listPlayers`, `getPlayerWalletAsAdmin` and `grantPlayerCurrency` in
 * the v1 contract.
 *
 * Listing players belongs to the platform rather than to the economy app, but a wallet means
 * nothing without the player it belongs to, so the economy screen is where an author finds one.
 */
export type PlayerProfile = {
  id: string;
  externalId: string;
  /** Null until the player chooses one. */
  displayName: string | null;
  createdAt: string;
  lastSeenAt: string;
};

export type PlayerPage = { players: PlayerProfile[]; total: number; nextCursor?: string | null };

export type PlayerBalance = { currency: string; amount: number; updatedAt: string };

export type PlayerWallet = { balances: PlayerBalance[] };

export type Grant = { currency: string; amount: number };

const PLAYERS = '/api/v1/admin/players';

export const PLAYERS_PER_PAGE = 25;

export const economy = {
  players: (cursor?: string): Promise<PlayerPage> => {
    const query = new URLSearchParams({ limit: String(PLAYERS_PER_PAGE) });
    if (cursor) {
      query.set('cursor', cursor);
    }
    return sendJson<PlayerPage>(`${PLAYERS}?${query.toString()}`);
  },

  wallet: (playerId: string): Promise<PlayerWallet> =>
    sendJson<PlayerWallet>(`${PLAYERS}/${segment(playerId)}/wallet`),

  grant: (playerId: string, grant: Grant): Promise<PlayerBalance> =>
    sendJson<PlayerBalance>(
      `${PLAYERS}/${segment(playerId)}/wallet/grant`,
      jsonBody('POST', { currency: grant.currency, amount: grant.amount }),
    ),
};

export type GrantCheck = { ok: true; grant: Grant } | { ok: false; problem: string };

/**
 * The form's two strings as a grant, or why not. Whole numbers only, written plainly: `1e3` is a
 * number to JavaScript and a typo to an author, and an amount past what a double holds exactly
 * would be sent as a different amount from the one typed.
 */
export function checkGrant(currency: string, amount: string): GrantCheck {
  const name = currency.trim();
  if (!name) {
    return { ok: false, problem: 'Name the currency to grant.' };
  }
  const value = Number(amount.trim());
  if (!/^\d+$/.test(amount.trim()) || !Number.isSafeInteger(value) || value <= 0) {
    return { ok: false, problem: 'The amount is a whole number above zero.' };
  }
  return { ok: true, grant: { currency: name, amount: value } };
}

/** The wallet with one balance replaced or added, in currency order. A new object. */
export function withBalance(wallet: PlayerWallet, balance: PlayerBalance): PlayerWallet {
  const others = wallet.balances.filter((existing) => existing.currency !== balance.currency);
  return {
    balances: [...others, balance].sort((a, b) => a.currency.localeCompare(b.currency)),
  };
}
