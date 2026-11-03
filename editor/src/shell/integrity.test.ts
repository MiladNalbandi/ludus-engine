import { describe, expect, it } from 'vitest';
import { createHash, webcrypto } from 'node:crypto';
import { IntegrityUnreadable, matchesIntegrity } from '@/shell/integrity';

/**
 * The check that stands between a plugin's bytes and the page: the bundle runs only if it hashes
 * to what the service recorded when the plugin was installed.
 */
const digest = (algorithm: string, data: ArrayBuffer) => webcrypto.subtle.digest(algorithm, data);

const bytes = (text: string): ArrayBuffer => new TextEncoder().encode(text).buffer as ArrayBuffer;

const sri = (algorithm: 'sha256' | 'sha384' | 'sha512', text: string) =>
  `${algorithm}-${createHash(algorithm).update(text).digest('base64')}`;

describe('matchesIntegrity', () => {
  it('accepts bytes whose sha384 is the recorded one', async () => {
    await expect(
      matchesIntegrity(bytes('export default 1'), sri('sha384', 'export default 1'), digest),
    ).resolves.toBe(true);
  });

  it('refuses bytes that differ by one character', async () => {
    await expect(
      matchesIntegrity(bytes('export default 2'), sri('sha384', 'export default 1'), digest),
    ).resolves.toBe(false);
  });

  it('judges by the strongest algorithm listed, as Subresource Integrity does', async () => {
    // A matching sha256 does not rescue a sha512 that does not match.
    const listed = `${sri('sha256', 'a')} ${sri('sha512', 'b')}`;
    await expect(matchesIntegrity(bytes('a'), listed, digest)).resolves.toBe(false);
    await expect(matchesIntegrity(bytes('b'), listed, digest)).resolves.toBe(true);
  });

  it('accepts any one of several values for the same algorithm', async () => {
    const listed = `${sri('sha384', 'old')} ${sri('sha384', 'new')}`;
    await expect(matchesIntegrity(bytes('new'), listed, digest)).resolves.toBe(true);
  });

  it('refuses an integrity it cannot read, rather than skipping the check', async () => {
    for (const unreadable of ['', 'md5-abc', 'sha384', 'sha384-@@@', 'nonsense']) {
      await expect(
        matchesIntegrity(bytes('a'), unreadable, digest),
        unreadable,
      ).rejects.toBeInstanceOf(IntegrityUnreadable);
    }
  });

  it('refuses to check at all without the browser digest, outside a secure context', async () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
    Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true });
    try {
      await expect(matchesIntegrity(bytes('a'), sri('sha384', 'a'))).rejects.toThrow(
        /secure context/,
      );
    } finally {
      if (original) {
        Object.defineProperty(globalThis, 'crypto', original);
      }
    }
  });
});
