# Contracts

The wire format, defined once.

`schemas/wave/v1.json` is a JSON Schema (draft 2020-12) describing a **wave**: a timed
arrangement of entity spawns, movement and fire behaviour. It is the agreement between three
parties that are built and deployed separately — the editor that authors a document, the engine
that validates and serves it, and the game client that reads it.

It lives here rather than in any of them because the alternative is three copies, and three
copies drift. Specifically:

- the engine copies it into its jar at build time (`engine-contracts`) and validates every
  document against it before storing;
- the editor consumes it as the npm workspace package `@ludus/contracts` and generates its
  TypeScript types from it, so the types cannot disagree with the contract;
- `samples/waves/` is validated against it on every build, in both Java and JavaScript, which
  is what keeps the two validators honest about the same file.

Licensed **Apache-2.0**, separately from the engine. Speaking a protocol should not require a
licence.

## Changing the schema

Additive changes — a new optional field, a new enum value — do not bump `schema_version`.

Removals, renames and redefinitions do. The compatibility rule clients rely on is that a client
ignores any document whose `schema_version` exceeds the version it was built against and plays
the rest: one unreadable wave costs one wave, never the session. That only holds if the version
is bumped honestly.
