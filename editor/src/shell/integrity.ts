/**
 * Does a bundle match the integrity the service recorded when the plugin was installed?
 *
 * The value is in Subresource Integrity form, `sha384-<base64>`, possibly several separated by
 * spaces. As SRI does, only the strongest algorithm present counts, and the bytes match if any
 * value for that algorithm is their digest. A value this code cannot read at all is a refusal, not
 * a pass: a check that waves through what it does not understand is no check.
 *
 * The browser's digest is `crypto.subtle`, which exists only in a secure context — HTTPS, or
 * `localhost`. An editor served over plain HTTP from any other address cannot check a bundle, and
 * so does not run one; it says why, in the rail.
 */
const ALGORITHMS = { sha256: 'SHA-256', sha384: 'SHA-384', sha512: 'SHA-512' } as const;
const STRENGTH: readonly (keyof typeof ALGORITHMS)[] = ['sha512', 'sha384', 'sha256'];

type Algorithm = keyof typeof ALGORITHMS;

export type Digest = (algorithm: string, data: ArrayBuffer) => Promise<ArrayBuffer>;

export class IntegrityUnreadable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'IntegrityUnreadable';
  }
}

function browserDigest(): Digest {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new IntegrityUnreadable(
      'this page is not a secure context (HTTPS or localhost), so the browser cannot check ' +
        "the bundle's integrity; it was not run",
    );
  }
  return (algorithm, data) => subtle.digest(algorithm, data);
}

function parse(integrity: string): Map<Algorithm, string[]> {
  const found = new Map<Algorithm, string[]>();
  for (const token of integrity.trim().split(/\s+/)) {
    // An SRI value may carry options after a `?`; none are defined, and they are ignored.
    const match = /^(sha256|sha384|sha512)-([A-Za-z0-9+/]+={0,2})(\?.*)?$/.exec(token);
    if (match) {
      const algorithm = match[1] as Algorithm;
      found.set(algorithm, [...(found.get(algorithm) ?? []), match[2] ?? '']);
    }
  }
  return found;
}

function base64(bytes: ArrayBuffer): string {
  let binary = '';
  for (const byte of new Uint8Array(bytes)) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export async function matchesIntegrity(
  data: ArrayBuffer,
  integrity: string,
  digest: Digest = browserDigest(),
): Promise<boolean> {
  const expected = parse(integrity);
  const algorithm = STRENGTH.find((candidate) => expected.has(candidate));
  if (!algorithm) {
    throw new IntegrityUnreadable(
      `the service recorded an integrity this editor cannot read (${JSON.stringify(integrity)})`,
    );
  }
  const actual = base64(await digest(ALGORITHMS[algorithm], data));
  return (expected.get(algorithm) ?? []).includes(actual);
}
