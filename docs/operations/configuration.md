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
| `/api/v1/admin/**` | no | Administrators only |
| everything else | no | Any valid credential; deny-by-default for anything unnamed |

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
