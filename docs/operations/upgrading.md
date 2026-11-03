# Upgrading

## The promise, from `1.0.0` onwards

The HTTP contract in [`docs/api/openapi-v1.json`](../api/openapi-v1.json) is frozen. From `1.0.0`:

- **A breaking change costs a major version.** Removing a path, an operation, a response field or an
  enum value, or making an optional request field required, is a `2.0.0`.
- **Anything additive is a minor version.** New endpoints, new optional fields, new enum values.
- **Fixes are patches.**

This is enforced rather than promised. `docs/api/openapi-v1.json` is the contract as it stood at
`1.0.0`, and `service/tests/integration/test_frozen_contract.py` holds the service to it on every
build: every operation is routed and called at its path, every request schema's properties are
accepted, every response schema's properties are present, and the fields that were optional stay
optional. Adding things says nothing, which is what makes it worth reading when it does speak.
While the Java engine was here, `FrozenContractTest` did the same by comparing generated documents;
R9 replaced it ([docs/platform/r9.md](../platform/r9.md)).

If you are looking at that test failing and the change is genuinely wanted: the answer is a major
version and a new baseline, not an edit to the test.

### What is not covered

**The database schema is not part of the contract.** Migrations run automatically on start and are
expected to change; what is promised is that they run forwards without you doing anything.

**The editor is not part of the contract.** It is a client of the same API you are, and it moves
with the service.

**`schema_version` inside a wave document is its own thing.** It is a property of the content format
and moves independently of the HTTP version — a client ignores any wave whose `schema_version`
exceeds what it was built against and plays the rest, so one unreadable wave costs one wave rather
than the session.

## Upgrading a deployment

```bash
cd deploy
docker compose pull
docker compose up -d
```

Migrations run on start. Watch the logs the first time:

```bash
docker compose logs -f service
```

### Before you upgrade

- **Back up the database.** Migrations run forwards and there is no automatic rollback.
- **Back up the volumes.** `wavemaker-blobs` holds uploaded audio and sprites that are *not* in
  the database, and `wavemaker-plugins` the installed plugins, so a database dump alone does not contain them. Losing them leaves rows describing
  files that are gone.
- **Read the changelog** for the versions you are skipping, not only the one you are going to.

## Version-specific notes

### From the Java engine to WaveMaker

The Python service answers the same v1 contract, so clients need no change. The deployment does:

- **The settings are renamed.** Every `LUDUS_*` setting of the Java engine is gone; the service
  reads `WAVEMAKER_*`. Start from the new `deploy/.env.example` rather than editing an old `.env`.
  The editor's own two settings keep their `LUDUS_` names.
- **The image is a different one**, `ghcr.io/miladnalbandi/wavemaker`, and the compose service is
  called `service`, not `engine`. `/actuator/health` is now `/health`.
- **The data does not move by itself.** The Python schema is built by its own migrations, from
  empty, on new volumes (`wavemaker-db`, `wavemaker-blobs`, `wavemaker-plugins`); it never reads a
  Java database, and a Python service pointed at one fails its first migration rather than mixing
  the two. Export what you need from the Java engine first — waves through the API, and
  `scripts/import-waves.mjs` to bring them in — or keep running the last Java release. There is no
  migration tool yet.

### To `1.0.0`

**No migration steps.** `1.0.0` adds no schema changes over `0.4.0`; it freezes the contract, fills
out the documentation and starts honouring semantic versioning. If you are running `0.4.0` you can
upgrade in place.

If you are coming from earlier than `0.4.0`, the migrations run in order and there is nothing to do
by hand — but the two volumes above did not exist before `0.2.0` and `0.4.0` respectively, so a
compose file older than those will not mount them. Take `deploy/docker-compose.yml` from this
release.

### Before `1.0.0`

Versions below `1.0.0` made no compatibility promise and the contract moved between them. There is
no supported upgrade path *between* pre-`1.0.0` versions beyond running the migrations in order,
which does work — the promise starts here, it does not apply retroactively.

## Downgrading

There is no supported downgrade. Migrations only run forwards, so going back means restoring the
backup you took before upgrading — which is the reason the list above starts with taking one.
