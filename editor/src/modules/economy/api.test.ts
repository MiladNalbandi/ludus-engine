import { describe, expect, it } from 'vitest';
import { checkGrant, economy, withBalance, type PlayerWallet } from '@/modules/economy/api';
import { json, mockEngine } from '@/test/engine';

const player = {
  id: '0b8f5f0e-8f4e-4c55-9d38-1f1b8f0a0001',
  externalId: 'device-1',
  displayName: 'Ada',
  createdAt: '2026-01-01T00:00:00Z',
  lastSeenAt: '2026-01-03T00:00:00Z',
};

describe('the economy calls', () => {
  it('pages players with listPlayers, passing the cursor it was handed', async () => {
    const sent = mockEngine({
      'GET /api/v1/admin/players': json({ players: [player], total: 41, nextCursor: 'c2' }),
    });

    const first = await economy.players();
    await economy.players('c2');

    expect(first).toEqual({ players: [player], total: 41, nextCursor: 'c2' });
    expect(sent[0]?.query.get('cursor')).toBeNull();
    expect(sent[0]?.query.get('limit')).toBe('25');
    expect(sent[1]?.query.get('cursor')).toBe('c2');
  });

  it("reads a player's wallet with getPlayerWalletAsAdmin", async () => {
    const wallet = { balances: [{ currency: 'coins', amount: 10, updatedAt: '2026-01-03T00:00:00Z' }] };
    const sent = mockEngine({ [`GET /api/v1/admin/players/${player.id}/wallet`]: json(wallet) });

    await expect(economy.wallet(player.id)).resolves.toEqual(wallet);
    expect(sent).toHaveLength(1);
  });

  it('grants with grantPlayerCurrency: currency and amount, and nothing else', async () => {
    const balance = { currency: 'coins', amount: 60, updatedAt: '2026-01-04T00:00:00Z' };
    const sent = mockEngine({
      [`POST /api/v1/admin/players/${player.id}/wallet/grant`]: json(balance),
    });

    await expect(economy.grant(player.id, { currency: 'coins', amount: 50 })).resolves.toEqual(balance);
    expect(sent[0]?.contentType).toBe('application/json');
    expect(sent[0]?.body).toEqual({ currency: 'coins', amount: 50 });
  });

  it("surfaces the engine's reason when a grant is refused", async () => {
    mockEngine({
      [`POST /api/v1/admin/players/${player.id}/wallet/grant`]: json(
        { detail: 'that balance would not fit' },
        422,
      ),
    });

    await expect(economy.grant(player.id, { currency: 'coins', amount: 1 })).rejects.toThrow(
      'that balance would not fit',
    );
  });
});

describe('checking a grant before it is sent', () => {
  it('accepts a currency and a positive whole amount', () => {
    expect(checkGrant(' coins ', '50')).toEqual({ ok: true, grant: { currency: 'coins', amount: 50 } });
  });

  it('refuses a missing currency', () => {
    expect(checkGrant('  ', '5')).toEqual({ ok: false, problem: 'Name the currency to grant.' });
  });

  it('refuses an amount that is not a positive whole number', () => {
    for (const amount of ['', '0', '-3', '2.5', '1e3', 'ten', String(Number.MAX_SAFE_INTEGER + 2)]) {
      expect(checkGrant('coins', amount)).toEqual({
        ok: false,
        problem: 'The amount is a whole number above zero.',
      });
    }
  });
});

describe('folding a granted balance into the wallet on screen', () => {
  const wallet: PlayerWallet = {
    balances: [
      { currency: 'coins', amount: 10, updatedAt: 'a' },
      { currency: 'gems', amount: 2, updatedAt: 'a' },
    ],
  };

  it('replaces the balance it changed', () => {
    expect(withBalance(wallet, { currency: 'coins', amount: 60, updatedAt: 'b' }).balances).toEqual([
      { currency: 'coins', amount: 60, updatedAt: 'b' },
      { currency: 'gems', amount: 2, updatedAt: 'a' },
    ]);
  });

  it('adds a currency the player did not hold, in name order', () => {
    expect(
      withBalance(wallet, { currency: 'dust', amount: 5, updatedAt: 'b' }).balances.map((b) => b.currency),
    ).toEqual(['coins', 'dust', 'gems']);
  });

  it('leaves the wallet it was given untouched', () => {
    withBalance(wallet, { currency: 'coins', amount: 99, updatedAt: 'b' });

    expect(wallet.balances[0]?.amount).toBe(10);
  });
});
