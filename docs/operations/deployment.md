# Deployment

WaveMaker is one service and one PostgreSQL database, plus the editor if you want it. No broker,
no second backend, no orchestrator required. That ceiling is deliberate: it should be possible
to run this on a small VM for a game that is not yet successful.

## What you need

- A container runtime
- PostgreSQL 16 (the compose file brings its own; in production, use a managed one you can back up)
- Disk for uploaded files, mounted as a volume
- A reverse proxy terminating TLS

## The image

Built from `deploy/Dockerfile.service` and published as `ghcr.io/miladnalbandi/wavemaker`,
multi-architecture (amd64 and arm64), by the release workflow after the full test suite passes.

**Pin a release tag.** `latest` moves, and an image that changes under you during an unrelated
restart is a bad night. `deploy/.env` has `WAVEMAKER_VERSION` for exactly this.

The container runs as uid 1001, one `uvicorn` process on port 8080. It migrates the database as
it starts, so run one process per database while it does; two starting at the same moment would
both try to migrate. FFmpeg is not in the standard image; build with `WITH_FFMPEG=true` if you
want audio mixing.

## Configuration

Every setting is an environment variable; see the [configuration reference](configuration.md).
The ones that matter on day one:

| | |
|---|---|
| `WAVEMAKER_DATABASE_URL` | Where PostgreSQL is. Compose builds it from `WAVEMAKER_DB_*` |
| `WAVEMAKER_JWT_SECRET` | Required. `openssl rand -base64 48` |
| `WAVEMAKER_BLOB_DIRECTORY` | Required for uploads. Must be a volume |
| `WAVEMAKER_VERSION` | Pin it |

## Two things people get wrong

**Leaving uploads inside the container.** Audio and sprites are files, not rows. If the blob
directory is not a volume, everything works until the next deploy, and then every file is gone
while the database still lists it. The compose file mounts `wavemaker-blobs` for this, and CI
proves it by replacing the container and reading an upload back. Installed plugins are on a
volume for the same reason.

**Publishing the service port to the internet without a proxy.** The compose file publishes the
service and the editor on `127.0.0.1`. `/health` and `/docs` are open by design and name every
app and its version. The editor never needs the service to be public at all: it reaches it on the
compose network.

## Database

Migrations run automatically at startup and run forwards only. Take a backup before upgrading.

## Upgrading

1. Read the release notes and `CHANGELOG.md`
2. Back up the database and the volumes
3. Change the pinned tag and recreate the container

Rolling back means restoring the backup, because migrations are forward-only. Backups are the
rollback plan; there is no other one.

## Health checks

`/health` answers `200` with the platform version and every loaded app once the service has
migrated and is serving. The image's own `HEALTHCHECK` calls it, and compose starts the editor
only after it passes.
