/**
 * Generates the wave TypeScript types from the JSON Schema the engine validates against.
 *
 * The schema at contracts/schemas/wave/v1.json is the single source of truth, and it is the engine
 * that enforces it. Hand-written types beside it are a second, unenforced copy that drifts, and
 * drifts quietly: the editor keeps compiling, the engine keeps rejecting, and the error arrives as
 * a 422 about a field the author cannot see in their form.
 *
 * `--check` regenerates into memory and compares. CI runs that, so a schema change with stale types
 * fails the build rather than the save.
 */
import { compileFromFile } from 'json-schema-to-typescript';
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const SCHEMA = resolve(here, '..', '..', 'contracts', 'schemas', 'wave', 'v1.json');
const OUTPUT = resolve(here, '..', 'src', 'lib', 'wave-schema.ts');

const BANNER = `// SPDX-License-Identifier: AGPL-3.0-or-later
//
// GENERATED FROM contracts/schemas/wave/v1.json -- DO NOT EDIT.
//
// Regenerate with \`npm run generate:types\` in editor/. CI runs \`npm run verify:types\` and fails
// on any difference, so editing this by hand is not a shortcut, it is a broken build.
`;

async function generate(): Promise<string> {
  if (!existsSync(SCHEMA)) {
    throw new Error(`the wave schema is not at ${SCHEMA}`);
  }
  const compiled = await compileFromFile(SCHEMA, {
    bannerComment: '',
    additionalProperties: false,
    style: { singleQuote: true, printWidth: 100 },
  });
  return `${BANNER}\n${compiled}`;
}

async function main(): Promise<void> {
  const generated = await generate();
  const checking = process.argv.includes('--check');

  if (!checking) {
    await writeFile(OUTPUT, generated, 'utf8');
    console.log(`wrote ${OUTPUT}`);
    return;
  }

  if (!existsSync(OUTPUT)) {
    console.error(`${OUTPUT} does not exist. Run: npm run generate:types`);
    process.exit(1);
  }
  const committed = await readFile(OUTPUT, 'utf8');
  if (committed !== generated) {
    console.error(
      [
        'The generated wave types are out of date with contracts/schemas/wave/v1.json.',
        '',
        'The schema changed and these types did not, which means the editor is compiling',
        'against fields the engine no longer accepts, or missing ones it now requires.',
        '',
        '  cd editor && npm run generate:types',
      ].join('\n'),
    );
    process.exit(1);
  }
  console.log('the generated wave types match the schema');
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
