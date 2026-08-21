# Deployment

Ludus is one application and one PostgreSQL database. No broker, no second service, no
orchestrator required. That ceiling is deliberate: it should be possible to run this on a small
VM for a game that is not yet successful.

## What you need

- A container runtime
- PostgreSQL 16 (the compose file brings its own; in production, use a managed one you can back up)
- A reverse proxy terminating TLS

## The image

Published to `ghcr.io/miladnalbandi/ludus-engine`, multi-architecture (amd64 and arm64).

**Pin a release tag.** `latest` moves, and an image that changes under you during an unrelated
restart is a bad night. `deploy/.env` has `LUDUS_VERSION` for exactly this.

The container runs as a non-root user and sizes its heap from the container's memory limit
(`-XX:MaxRAMPercentage=75`) rather than a number guessed at build time — so give it a limit and
it will respect it.

## Configuration

Every setting is an environment variable; see the [configuration reference](configuration.md).
The ones that matter on day one:

| | |
|---|---|
| `LUDUS_DB_*` | Connection details. The password is required. |
| `LUDUS_PORT` | Defaults to 8080 |
| `LUDUS_VERSION` | Pin it |

From `v0.1.0` a JWT signing secret becomes **required**, and the engine will refuse to start in
production without one. There will be no default value — a default signing secret in a public
repository becomes an exploit within a week of anyone using it.

## Two things people get wrong

**Exposing the metrics endpoint.** `/actuator/prometheus` is open to anything that can reach the
port, because a scraper is infrastructure rather than a user. It exposes request rates, error
counts and database pool state. Keep it unreachable from the public internet — either bind the
service to your internal network and let the proxy forward only what should be public, or block
the path at the proxy. This is the single most likely misconfiguration of a fresh install.

The compose file publishes the engine on `127.0.0.1` for this reason. If you change that to
`0.0.0.0`, know what you are doing.

**Setting `ddl-auto` to `update`.** The schema is owned by Flyway. Hibernate runs with `validate`
and will refuse to start when an entity and a migration disagree — that failure is the feature.
`update` will silently reshape your production schema to match whatever the code happens to say.

## Database

Migrations run automatically at startup and are forward-only. Take a backup before upgrading
across a minor version; the project will document any migration that is not trivially reversible.

Before `1.0.0` the schema can change between releases without a documented upgrade path. That
changes at `1.0.0` — see the [roadmap](../roadmap.md).

## Upgrading

1. Read the release notes and `CHANGELOG.md`
2. Back up the database
3. Change the pinned tag and recreate the container

Rolling back means restoring the backup, because migrations are forward-only. Backups are the
rollback plan; there is no other one.

## Health checks

| | |
|---|---|
| Liveness | `/actuator/health/liveness` |
| Readiness | `/actuator/health/readiness` |
| Combined | `/actuator/health` |

Readiness includes the database, so a probe against it will correctly refuse traffic while the
database is unreachable.
