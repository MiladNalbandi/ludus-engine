# The content model

> The schema described here **exists today** and is validated on every build. The HTTP API that
> serves it arrives in `v0.2.0` — [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8).
> Endpoint shapes below are the planned design, not something you can call yet.

## Content is documents, not columns

A piece of content — today a *wave*, later also a map or a level — is a JSON document validated
against a published JSON Schema. The database indexes what it needs to query (identifier, name,
order, publication state) and stores the document itself **verbatim**.

The schema, not a Java class, is the contract.

This is what lets the content model grow without a migration every time a behaviour gains a
parameter, and what lets an editor and a game client agree on a shape without either importing
the other's code. It is also what makes the plugin work in
[#12](https://github.com/MiladNalbandi/ludus-engine/issues/12) a decomposition rather than a
rewrite.

## One schema, three consumers

`contracts/schemas/wave/v1.json` lives in exactly one place and is used by three parties that are
built and deployed separately:

- the **engine** copies it into its jar at build time and validates every document before storing
- the **editor** consumes it as an npm workspace package and generates its TypeScript types from
  it, so the types cannot disagree with the contract
- **`samples/waves/`** is validated against it on every build, in both Java and JavaScript, which
  is what keeps the two validators honest about the same file

There is no second copy to drift. `contracts/` is Apache-2.0, separately from the AGPL engine —
speaking a protocol should not require a licence.

## Publication is separate from saving

**Editing content never affects players.** Only published content is served on the public routes,
and to an unauthenticated client a draft is indistinguishable from something that does not exist —
`404`, not `403`.

This is one of the few places where the design is deliberately unhelpful, and it is worth it. The
alternative is that saving a half-finished level ships it to everyone currently playing.

The publication flag lives on a column, not only inside the document. The column is authoritative;
the document mirrors it so that a document read in isolation still says whether it was live.

## Derived fields are derived, not submitted

Ordering is read from inside the document (`progression_config.order`) rather than accepted as a
request field, and a collision with another document's order is a validation error pointing at
that exact path.

There is also a database uniqueness constraint on it. The application checks first so the error
message is useful; the constraint exists so that two concurrent writes cannot both succeed. Belt
and braces, because the friendly check alone is a race.

## Schema versioning, and the rule clients rely on

Documents carry a `schema_version`: a monotonic integer describing the contract generation.

- **Additive changes** — a new optional field, a new enum value — do **not** bump it
- **Removals, renames and redefinitions** do

The rule every client implements: *ignore any document whose `schema_version` exceeds the version
you were built against, and play the rest.* One unreadable piece of content costs one piece of
content, never the session.

That only holds if the version is bumped honestly. A client that hard-fails on unknown content
turns every additive change into a forced update, which is why the compatibility rule is part of
the contract rather than advice.

## Validation is strict, on purpose

The schema sets `additionalProperties: false` throughout. An unrecognised field is an error, not
something quietly carried along.

That is stricter than it needs to be for a single application, and correct for a published
contract with independent client implementations: a typo in a field name should fail at authoring
time, not manifest as a behaviour that silently does nothing in the game.

Some things a JSON Schema cannot express — comparing sibling subtrees, for instance, to check that
the several fields describing a piece of content's length agree with each other. Those live as
explicit rules alongside the schema validation, and they report errors at the same JSON Pointer
paths so an editor can attach every error to the field that caused it.
