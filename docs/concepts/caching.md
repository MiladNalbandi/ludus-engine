# Caching and change detection

> The protocol described here **exists today**. The routes are under `/api/v1/public`, and the
> client SDK ([#16](https://github.com/MiladNalbandi/ludus-engine/issues/16)) is designed against
> it.
>
> The poll was written here as `GET /app/status` before it was built and is now
> `GET /api/v1/public/status`, so that the whole public surface shares one prefix. No client had
> been written against the old path — this was the last moment that rename was free.

A game client fetches content over the network and caches it. Getting this wrong is expensive in
a way that is easy to miss: it does not break anything, it just makes every player re-download
the catalogue on every launch. On mobile that is a real bandwidth bill and real one-star reviews.

## Two signals, one source

There are two ways a client learns that content changed:

1. **A poll.** `GET /api/v1/public/status` returns a content hash covering all published content.
   Cheap to call — it reads ids and timestamps and never loads a document — and served
   `Cache-Control: no-store` so it is never itself cached.
2. **HTTP validation.** Every public content response carries an `ETag`. A client re-requests with
   `If-None-Match` and gets `304 Not Modified` when nothing changed.

**Both are derived from the same function.** This is the single most important thing on this page.

If the status hash and the ETags were computed differently, a client could be told "something
changed" by the poll, refetch, and be handed a `304` by an HTTP cache validating against the other
signal — or the reverse: told nothing changed while a cache holds stale bytes. That bug is very
hard to see and very annoying to debug, so the two are the same function by construction.

## Why stored bytes must be stable

The ETag for a raw content response is a hash of the **stored bytes**.

So the bytes have to be stable. If the write path deserialised a document and re-serialised it,
the bytes would change for reasons that have nothing to do with the content — different null
handling, different key ordering, `1.0` versus `1`. Storing the document as `jsonb` would change
them again, because PostgreSQL normalises whitespace and reorders keys.

Either would mean every save produces a new ETag even when the author changed nothing, and every
client re-downloads everything.

The engine therefore stores the received bytes verbatim in a text column, with a *generated*
`jsonb` column alongside for indexing, and derives every indexed field by **reading** the document
rather than by re-serialising it. That is `config_json` and `config` in `V4__wave.sql`; the
generated column is PostgreSQL-specific and lives in `db/vendor/postgresql` so that the shared
schema stays one schema rather than two hand-maintained dialects. There is exactly one exception — stamping `schema_version` when a
document omits it — and it is a surgical edit to the parsed tree, documented as the one
non-byte-preserving path.

`WaveRoundTripByteStabilityTest` guards this permanently: save a document written with awkward but
legal formatting — odd whitespace, keys out of order, an explicit `1.0` — read it back, and assert
the bytes are identical; re-save an identical body and assert the hash did not move. Confirmed by
adding a deserialise-and-re-serialise step to the write path and watching it fail.

## What a well-behaved client does

1. On launch, `GET /api/v1/public/status`. Compare the content hash to the cached one.
2. Unchanged → play from cache. No further requests.
3. Changed → `GET /api/v1/public/waves`, then fetch changed documents from
   `/api/v1/public/waves/{id}/raw` with `If-None-Match` from the cache.
4. Store the raw bytes and the ETag together. The ETag is only useful alongside the bytes it
   validates.

The `If-None-Match` handling on the server tolerates what real clients and proxies actually send:
weak validators (`W/"…"`), quoted and unquoted forms, comma-separated lists, and `*`. This is
unglamorous and it is exactly the sort of thing that silently disables caching for one platform's
HTTP stack when it is not handled. It lives in `EntityTags` with twenty-five table rows, one per
form seen in the wild, and comparison is deliberately weak — `W/"x"` matches `"x"`, because strong
comparison exists for byte ranges and nothing here serves ranges.

That the two signals cannot disagree is asserted directly: a test fetches the poll and the list and
requires the hash and the ETag to be the same string. Computing the list ETag beside the poll rather
than from the same function fails it.

## Offline

Because the cache holds raw bytes that were valid when stored, a client that has fetched
successfully once can start and play with no network at all. Content that fails to validate — or
carries a `schema_version` newer than the client understands — is skipped individually rather than
failing the load.
