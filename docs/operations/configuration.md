# Configuration reference

Every setting is an environment variable. `deploy/.env.example` lists them with safe defaults
and no real values.

## Database

| Variable | Default | |
|---|---|---|
| `LUDUS_DB_HOST` | `localhost` | |
| `LUDUS_DB_PORT` | `5432` | |
| `LUDUS_DB_NAME` | `ludus` | |
| `LUDUS_DB_USER` | `ludus` | |
| `LUDUS_DB_PASSWORD` | *(none)* | Required in any real deployment |

The schema is owned by Flyway. Hibernate runs with `ddl-auto: validate` and will refuse to
start if an entity and a migration disagree — that is intentional, and a failed boot is the
correct outcome. Never set it to `update`.

## Server

| Variable | Default | |
|---|---|---|
| `LUDUS_PORT` | `8080` | |
| `LUDUS_LOG_LEVEL` | `INFO` | Engine logging only; the root logger stays at `INFO` |
| `LUDUS_VERSION` | `0.0.1-SNAPSHOT` | Reported by `/actuator/info` and in the OpenAPI document. The release workflow sets it; override it only if you build your own images |

## Tenancy

| Variable | Default | |
|---|---|---|
| `LUDUS_TENANCY_MODE` | `single` | `single` resolves every request to the default project |

Every table carries a project identifier from the first migration, even though a self-hosted
install only ever has one project. That is what makes hosting several projects later a
configuration change rather than a rewrite of every query, foreign key and URL.

In `single` mode the engine creates that project on first start, under the slug `default`, and
logs the identifier it chose. The check runs on every start and is idempotent, so a restart finds
the project rather than adding one. You are never asked to name it and it does not appear in any
URL.

Two starts fail rather than continue:

- The value is neither `single` nor `multi`. A typo in this setting is not something to guess at.
- The mode is `single` and the database already holds a project that is not `default`. That means
  either the mode was switched or the engine is pointed at the wrong database, and adding a second
  project to find out which would be the wrong answer to both.

`multi` is accepted and provisions nothing. Nothing routes to it yet — the hosted deployment is
`v2.0.0`, [#17](https://github.com/MiladNalbandi/ludus-engine/issues/17) — so today it produces an
engine with no project, which is only useful for confirming that the switch exists.

## Audio

| Variable | Default | |
|---|---|---|
| `LUDUS_AUDIO_DIRECTORY` | *(none)* | Where clip bytes are written. Required once audio is used |
| `LUDUS_AUDIO_MAX_FILE_SIZE` | `64MB` | Refused above this, per file and per request |
| `LUDUS_AUDIO_MIXER_MODE` | `none` | `ffmpeg` enables mixing. Needs the `ludus-engine-ffmpeg` image |
| `LUDUS_AUDIO_MIXER_TIMEOUT` | `60s` | A hard stop on one mix |
| `LUDUS_AUDIO_MIXER_MAX_TRACKS` | `8` | Tracks per mix |

**Clip bytes are not in the database.** Metadata is; the bytes are files on a disk you mount. A
database row holding a 40 MB track is read into memory to be served, which is the thing the whole
audio path is built to avoid, and it makes every backup carry the music.

The compose file mounts a named volume at `/var/lib/ludus/audio` and sets the variable to match.
If you run the engine some other way, point it at a directory that persists across deploys —
a container's own filesystem does not, and the clips would disappear on the next release while
the database went on listing them.

The directory is checked for existence and writability at startup, and the engine refuses to
start if it fails. Discovering that at boot is better than discovering it from the first editor
who tries to upload a track.

**Mixing is off, and needs a different image.** Combining clips into one needs FFmpeg, which the
standard image deliberately does not carry: it is a large dependency with its own vulnerability
history, and a self-hosted install should not have to acquire a media toolchain to get a working
engine. `POST /api/v1/admin/audio/mix` answers `503` with a message naming the image and the
variable. Uploading and serving work either way.

Where it is enabled, the subprocess is run with an **argv list and no shell**. The codebase Ludus
was extracted from built an FFmpeg command as a string and passed it to a shell with interpolated
filenames, which gave any authenticated editor user command execution on the container. Here no
client string ever becomes an argument — inputs are written to a per-job temporary directory under
names derived from their index — there is a hard timeout, an output size cap, and the tool's own
output is logged rather than returned, because it names paths inside the container.

**Nothing is streamed into memory at either end**, and that is enforced by a test rather than a
convention: `AudioStreamingIT` pushes a clip larger than the entire heap through storage and back
out over HTTP, in a JVM capped at 256 MB. If it ever fails with `OutOfMemoryError`, the fix is on
the code path, not in the heap size.

## Security

| Variable | Default | |
|---|---|---|
| `LUDUS_JWT_SECRET` | *(none)* | **Required.** The signing key for access tokens |
| `LUDUS_JWT_ISSUER` | `ludus` | Written into tokens and required when verifying them |
| `LUDUS_JWT_ACCESS_TTL` | `15m` | How long an access token lasts |
| `LUDUS_JWT_REFRESH_TTL` | `30d` | How long a refresh token lasts |
| `LUDUS_ADMIN_EMAIL` | *(none)* | The first administrator |
| `LUDUS_ADMIN_PASSWORD` | *(none)* | The first administrator's password |

There is no default signing secret and there will not be one. A default published in a public
repository is a working forgery tool for every install that kept it, and telling operators to
change it has never been sufficient. The engine refuses to start without one:

```
LUDUS_JWT_SECRET is not set.

There is no default, deliberately: a signing secret published in a public repository lets
anyone forge a token for every install that kept it. Generate one and keep it out of version
control:

    openssl rand -base64 48
```

Anything shorter than 32 bytes is refused too, because HS256 needs a 256-bit key.

**The two lifetimes are a trade, not a pair of arbitrary numbers.** An access token is verified
by checking a signature and nothing else, which is what makes it fast — and also means it cannot
be revoked. `LUDUS_JWT_ACCESS_TTL` is therefore also the answer to *how long a stolen session
keeps working after someone signs out*. A refresh token is stored, so revoking it is immediate,
which is why it is allowed to last a month. Redeeming one revokes it and issues another, so a
stolen refresh token and the real one cannot both keep working.

**The administrator is seeded only into a project with no users.** Once a second account exists,
this configuration stops acting entirely: changing the password here will not reset a real
administrator's credentials, and removing the account will not see it quietly recreated on the
next deploy. Leaving both blank is allowed and merely logged — an install whose administrator
was created on a previous run does not need the password on hand at every restart.

**API keys are issued through the API, not configured.** `POST /api/v1/admin/api-keys` mints one
and returns it once; only a digest is stored, so it cannot be shown again by anyone, including
whoever runs the database. A key is always read-only, because a key ends up in a config file, a
git repository and a shipped game binary, and anything it can do should be assumed public.

## Endpoints and their exposure

| Path | Open | |
|---|---|---|
| `/actuator/health` | yes | Liveness and readiness. Called before any credential exists |
| `/actuator/info` | yes | Version metadata |
| `/actuator/prometheus` | yes | Metrics |
| `/api-docs`, `/docs` | yes | The API contract, not data |
| `/api/v1/auth/token` | yes | Signing in cannot require being signed in |
| `/api/v1/auth/refresh` | yes | The refresh token is itself the credential |
| `/api/v1/public/**` | yes | Published content and audio: what every copy of the game downloads |
| `/api/v1/admin/waves/**`, `/api/v1/admin/audio/**`, `/api/v1/admin/wave-levels/**`, `/api/v1/admin/app-config` | no | Editors and above |
| `/api/v1/admin/**` | no | Administrators only |
| everything else | no | Any valid credential; deny-by-default for anything unnamed |

`/api/v1/public/**` requires no credential on purpose. An API key that ships inside a game binary
is not a secret, and published content is by definition what every player downloads — demanding a
key there would stop nobody while suggesting a boundary that is not real. The routes stay in the
same filter chain as everything else rather than getting their own, so a caller that *does* send a
key is still identified; none is required. That is what keeps client identification, project
selection and rate limiting available later without reopening the question.

An anonymous request to a protected path gets `401`, and a request with a valid credential that
lacks the role gets `403`. The two are worth telling apart: one sends you to look at your token,
the other at your role.

**`/actuator/prometheus` is open to anything that can reach the port.** It is meant for a
scraper inside your deployment's network, and it exposes operational detail — request rates,
error counts, database pool state — that you should not hand to the public internet. Keep the
management port unreachable from outside, or put the path behind your reverse proxy. This is
the single most likely misconfiguration of a fresh install, so it is worth doing on day one.

Metrics export is enabled explicitly in `application.yml`. From Spring Boot 3.5 onwards it is
opt-in, and without that setting the scrape endpoint is never registered and quietly 404s.
