#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Imports wave documents into a running engine, all or nothing.
 *
 *   node scripts/import-waves.mjs --url http://localhost:8080 \
 *        --email admin@example.test --password '…' samples/waves/*.json
 *
 * Posts to POST /api/v1/admin/waves/bulk, which is transactional: one invalid document rejects the
 * whole import and nothing is written. That is the point of using it rather than a loop of single
 * saves -- a half-finished import leaves somebody working out which half landed, and whether
 * running it again would duplicate it.
 *
 * Imported waves are drafts. Nothing is published by being imported, because publishing a
 * half-reviewed catalogue to every player is not something a migration script should be able to do
 * by accident.
 *
 * No dependencies, on purpose: it runs with whatever Node an operator already has.
 */

import { readFile } from 'node:fs/promises';
import { basename } from 'node:path';

function usage(message) {
  if (message) console.error(`error: ${message}\n`);
  console.error(
    [
      'Import wave documents into a Ludus engine.',
      '',
      '  node scripts/import-waves.mjs [options] <file.json> [more.json …]',
      '',
      'Options:',
      '  --url <base>        engine base URL (default: http://localhost:8080)',
      '  --email <address>   an editor or administrator',
      '  --password <secret> their password',
      '  --token <jwt>       an access token, instead of email and password',
      '  --publish           publish each wave after importing (default: leave as drafts)',
      '  --dry-run           validate and report, write nothing',
      '',
      'Credentials may also come from LUDUS_EMAIL, LUDUS_PASSWORD or LUDUS_TOKEN.',
    ].join('\n'),
  );
  process.exit(message ? 2 : 0);
}

function parseArguments(argv) {
  const options = {
    url: process.env.LUDUS_URL ?? 'http://localhost:8080',
    email: process.env.LUDUS_EMAIL,
    password: process.env.LUDUS_PASSWORD,
    token: process.env.LUDUS_TOKEN,
    publish: false,
    dryRun: false,
    files: [],
  };

  for (let i = 0; i < argv.length; i++) {
    const argument = argv[i];
    switch (argument) {
      case '--url': options.url = argv[++i]; break;
      case '--email': options.email = argv[++i]; break;
      case '--password': options.password = argv[++i]; break;
      case '--token': options.token = argv[++i]; break;
      case '--publish': options.publish = true; break;
      case '--dry-run': options.dryRun = true; break;
      case '--help': case '-h': usage(); break;
      default:
        if (argument.startsWith('-')) usage(`unknown option ${argument}`);
        options.files.push(argument);
    }
  }
  return options;
}

async function signIn({ url, email, password, token }) {
  if (token) return token;
  if (!email || !password) {
    usage('supply --token, or --email and --password');
  }
  const response = await fetch(`${url}/api/v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    // The engine answers every authentication failure identically, so there is nothing more
    // specific to report and guessing would be misleading.
    throw new Error('those credentials were not accepted');
  }
  return (await response.json()).accessToken;
}

/** Reads each file, failing before anything is sent if one of them is not JSON at all. */
async function readDocuments(files) {
  const documents = [];
  for (const file of files) {
    const text = await readFile(file, 'utf8');
    try {
      JSON.parse(text);
    } catch (malformed) {
      throw new Error(`${file} is not valid JSON: ${malformed.message}`);
    }
    // The parsed value is discarded deliberately: the engine stores the bytes it receives, and
    // re-serialising here would change them -- and with them every client's cached ETag.
    //
    // Trimmed, because what is being sent is the document and not the file. A file's trailing
    // newline is formatting; the bulk endpoint trims it anyway when splitting the array, so
    // sending it would mean what came back never quite matched what went in.
    documents.push({ file, text: text.trim() });
  }
  return documents;
}

function reportViolations(body) {
  let problem;
  try {
    problem = JSON.parse(body);
  } catch {
    console.error(body);
    return;
  }
  console.error(`\n${problem.title ?? 'Rejected'}: ${problem.detail ?? ''}\n`);
  for (const violation of problem.violations ?? []) {
    // The pointer is prefixed with the document's index by the bulk endpoint, so "/2/name" means
    // the third file on the command line.
    console.error(`  ${violation.pointer || '(document)'}  ${violation.message}`);
  }
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.files.length === 0) usage('give at least one file');

  const documents = await readDocuments(options.files);
  console.log(`Read ${documents.length} document${documents.length === 1 ? '' : 's'}.`);

  if (options.dryRun) {
    for (const [index, document] of documents.entries()) {
      console.log(`  [${index}] ${basename(document.file)}  ${document.text.length} bytes`);
    }
    console.log('\nDry run: nothing was sent.');
    return;
  }

  const token = await signIn(options);
  const response = await fetch(`${options.url}/api/v1/admin/waves/bulk`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: `[${documents.map((d) => d.text).join(',')}]`,
  });

  if (!response.ok) {
    console.error(`\nThe import was refused (${response.status}). Nothing was written.`);
    reportViolations(await response.text());
    console.error(
      '\nThe bulk endpoint is all-or-nothing, so the catalogue is exactly as it was.\n' +
        'Indices in the pointers above are positions on the command line.',
    );
    process.exit(1);
  }

  const imported = await response.json();
  console.log(`\nImported ${imported.length} wave${imported.length === 1 ? '' : 's'} as drafts:`);
  for (const wave of imported) console.log(`  ${wave.id}  ${wave.name}  (order ${wave.order})`);

  if (!options.publish) {
    console.log('\nNothing was published. Publish when you have reviewed them:');
    console.log(`  curl -X POST ${options.url}/api/v1/admin/waves/<id>/publish -H "Authorization: Bearer …"`);
    return;
  }

  // Published one at a time, and deliberately after the import rather than as part of it: the
  // import is atomic, publication is not, and pretending otherwise would be worse than saying so.
  console.log('\nPublishing:');
  for (const wave of imported) {
    const published = await fetch(
      `${options.url}/api/v1/admin/waves/${encodeURIComponent(wave.id)}/publish`,
      { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
    );
    console.log(`  ${wave.id}  ${published.ok ? 'published' : `FAILED (${published.status})`}`);
  }
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exit(1);
});
