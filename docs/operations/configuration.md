# Configuration reference

Every setting is an environment variable. The service reads everything under the `WAVEMAKER_`
prefix; `deploy/.env.example` lists every one of them with safe defaults and no real values, and
`service/tests/unit/test_configuration_is_documented.py` fails the build when this page, that
file and the code disagree.

**An empty value is a value.** The service does not treat `WAVEMAKER_X=` as unset: an empty path
is a path, and an empty FFmpeg binary is refused at startup as not absolute. Comment out a setting
you do not want rather than leaving it blank. The compose file hands `deploy/.env` to the service
as written for exactly this reason.

## Database

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_DATABASE_URL` | *(none)* | A SQLAlchemy URL, `postgresql+psycopg://user:password@host:5432/name` |

Set by compose from the four values below, which compose reads to configure PostgreSQL as well:

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_DB_NAME` | `wavemaker` | |
| `WAVEMAKER_DB_USER` | `wavemaker` | |
| `WAVEMAKER_DB_PASSWORD` | *(none)* | **Required.** Compose refuses to start without it. It goes into the URL, so avoid `@ : / ? # %` |

PostgreSQL is the only database, deliberately. The content design rests on a `jsonb` column
generated from stored text and on a partial unique index, and a second dialect would mean either
two schemas or a rule enforced in production and unprovable in tests.

**The schema is migrated at startup, before anything is served.** The platform's own history
runs first, then each app that carries one, in name order. A process that answered requests
against a schema it had not been migrated to would read correctly and fail one write hours later,
in front of players. Run one service process per database while it starts; two starting at the
same moment would both try to migrate.

Without a database URL the service still starts, and says so honestly: the public catalogue is
empty, application configuration is `{}`, and every authoring route answers `503`.

## Server

The image runs `uvicorn` on port 8080, one process. These are read by compose, not the service:

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_PORT` | `8080` | Published on `127.0.0.1` only |
| `WAVEMAKER_EDITOR_PORT` | `3000` | The editor, also on `127.0.0.1` only |
| `WAVEMAKER_VERSION` | `latest` | The image tag. Pin a release in production |
| `WAVEMAKER_WITH_FFMPEG` | `false` | `true` builds the image with FFmpeg in it. See [Media](#media) |

## Project

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_PROJECT_SLUG` | `default` | The one project a self-hosted install serves |
| `WAVEMAKER_PROJECT_NAME` | `Default` | Its display name |

Every table carries a project identifier, even though a self-hosted install only ever has one
project. That is what makes hosting several later a configuration change rather than a rewrite
of every query, key and URL. The project is provisioned at startup, idempotently: a restart finds
it rather than adding one.

## Security

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_JWT_SECRET` | *(none)* | **Required** with a database. The key every token is signed with |
| `WAVEMAKER_ACCESS_TOKEN_MINUTES` | `15` | How long an account's access token lasts |
| `WAVEMAKER_REFRESH_TOKEN_DAYS` | `30` | How long a refresh token lasts |
| `WAVEMAKER_PLAYER_TOKEN_MINUTES` | `60` | How long a player session token lasts |
| `WAVEMAKER_ADMIN_EMAIL` | *(none)* | An administrator to create at startup |
| `WAVEMAKER_ADMIN_PASSWORD` | *(none)* | Their password |

There is no default signing secret and there will not be one. A default published in a public
repository is a working forgery tool for every install that kept it. The service refuses to start
without one, and refuses anything shorter than 32 bytes, because HS256 needs a 256-bit key:

```
openssl rand -base64 48
```

**The lifetimes are a trade, not arbitrary numbers.** An access token is verified by its
signature alone, which is what makes it fast and also means it cannot be revoked, so its lifetime
is also how long a stolen session keeps working after somebody signs out. A refresh token is
stored, as a digest, so revoking it is immediate. Redeeming one revokes it and issues another; if
an already-redeemed token comes back, every live session of that account is revoked, because a
lost race and a stolen copy look identical from here. A player token authorises writes to one
player's state and cannot be revoked, so it is short too.

**The administrator is created only when no account has that email**, and left alone when one
does. Changing the password here never resets a real administrator's credentials; clearing both
deletes nobody. A different email creates a second administrator.

**API keys are issued through the API, not configured.** `POST /api/v1/admin/api-keys` mints one
and returns it once; only a digest is stored. A key buys a player session and nothing else: it is
written into game builds, and anything it can do should be assumed public.

## Plugins

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_PLUGINS_DIRECTORY` | *(none)* | Where installed plugins live. The image sets `/var/lib/wavemaker/plugins`, a volume |
| `WAVEMAKER_PLUGIN_REGISTRY` | *(none)* | Where `wavemaker plugin install` finds packages. Read by the command only |
| `WAVEMAKER_TRUSTED_KEYS_DIRECTORY` | *(none)* | The public keys a plugin may be signed with, one PEM file per key |

Unset plugins directory means the service runs no plugins, which is a deliberate state; a
directory that is set and missing stops the service at startup. Unset trusted keys trusts nobody,
so nothing can be installed until somebody decides whose signature counts. Installing runs inside
the container, against the same settings the service has:

```bash
docker compose -f deploy/docker-compose.yml exec service \
  wavemaker plugin install quests@1.0.0
docker compose -f deploy/docker-compose.yml restart service
```

The registry and the keys have to be somewhere the container can read, so mount them and point
the two settings at the mount points. A plugin's code is imported when the service starts, hence
the restart.

## Media

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_BLOB_DIRECTORY` | *(none)* | Where uploaded audio and sprites are written. The image sets `/var/lib/wavemaker/blobs`, a volume |
| `WAVEMAKER_MEDIA_MAX_AUDIO_BYTES` | `67108864` | 64 MiB. A larger upload is refused |
| `WAVEMAKER_MEDIA_MAX_SPRITE_BYTES` | `16777216` | 16 MiB |
| `WAVEMAKER_MEDIA_FFMPEG_BINARY` | *(none)* | An absolute path to FFmpeg. Unset, mixing answers `503` |
| `WAVEMAKER_MEDIA_MIX_TIMEOUT_SECONDS` | `60` | A hard stop on one mix |
| `WAVEMAKER_MEDIA_MIX_MAX_TRACKS` | `8` | Tracks per mix |
| `WAVEMAKER_MEDIA_MIX_MAX_OUTPUT_BYTES` | `67108864` | A cap on what one mix may produce |

**Uploaded bytes are not in the database.** The rows describing them are; the bytes are files on
a disk you mount. The compose file mounts the `wavemaker-blobs` volume, and the directory is
checked for writability at startup, so a mistake is found while somebody is watching the deploy
rather than by the first author who uploads a track. Losing that volume loses every file while the
rows go on listing them, so it is a backup target next to the database.

**Mixing needs FFmpeg, which the standard image does not carry.** It is a large dependency with
its own vulnerability history, and a self-hosted install should not need a media toolchain to
work. Build with `WAVEMAKER_WITH_FFMPEG=true` and set `WAVEMAKER_MEDIA_FFMPEG_BINARY` to
`/usr/bin/ffmpeg`. Uploading and serving clips work either way. The binary is a path rather than a
name looked up on `PATH`, so "mixing works" never depends on what happens to be installed. It is
run with an argument list and no shell, on inputs written under names derived from their index,
with a timeout and an output cap, and what it prints is logged rather than returned.

## Content

| Variable | Default | |
|---|---|---|
| `WAVEMAKER_WAVE_SCHEMA` | the repository's `contracts/schemas/wave/v1.json` | The schema every wave is validated against. The image sets it to its own copy |

## Editor

The editor is a separate container with its own two settings, under the names it has always read.
Compose sets the first.

| Variable | Default | |
|---|---|---|
| `LUDUS_ENGINE_URL` | *(none)* | Where the editor's server reaches the service: `http://service:8080` on the compose network |
| `LUDUS_EDITOR_HTTPS` | `false` | `true` makes the refresh cookie `Secure`. Set it once the editor is served over HTTPS |

## Endpoints and their exposure

| Path | Open | |
|---|---|---|
| `/health` | yes | The platform version and every app that loaded. Called before any credential exists |
| `/openapi.json`, `/docs` | yes | The API description, not data |
| `/api/v1/auth/token` | yes | Signing in cannot require being signed in |
| `/api/v1/auth/refresh` | yes | The refresh token is itself the credential |
| `/api/v1/public/**` | yes | Published content, configuration, audio and sprites: what every copy of the game downloads |
| `POST /api/v1/public/players/session` | no | An API key. Minting a credential is not reading content |
| `/api/v1/player/**` | no | A player session token, and only for that player's own state |
| `/api/v1/admin/**` | no | An account's access token. Each route names the roles it admits |
| `/api/v1/me` | no | Any account's access token |

Under `/api/v1/admin`, reading drafts, levels and media is open to viewers; changing them, and
everything to do with players, items, boards, the XP curve and application configuration, needs an
editor or an administrator; API keys are for administrators only.

`/api/v1/public/**` requires no credential on purpose. An API key that ships inside a game binary
is not a secret, and published content is by definition what every player downloads.

**A player token is not an access token, and neither is an API key.** The two token kinds carry a
`typ` claim that each verifier requires, so a player cannot be read as an account with no role,
and a refresh token is not accepted as a bearer credential.

An anonymous request to a protected path gets `401`, and a credential that lacks the role gets
`403`. One sends you to look at your token, the other at your role.

**`/health` and `/docs` are open to anything that can reach the port.** Neither exposes data, but
`/health` names every app and its version. Keep the port on loopback, as compose does, and put a
reverse proxy in front before exposing the service.
