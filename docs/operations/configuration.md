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

## Security

There is nothing to configure here yet — identity arrives in `v0.1.0`, at which point a JWT
signing secret becomes **required** and the engine will refuse to start in production without
one. There will be no default value, because a default signing secret in a public repository
becomes an exploit within a week of anyone using it.

## Endpoints and their exposure

| Path | Open | |
|---|---|---|
| `/actuator/health` | yes | Liveness and readiness. Called before any credential exists |
| `/actuator/info` | yes | Version metadata |
| `/actuator/prometheus` | yes | Metrics |
| `/api-docs`, `/docs` | yes | The API contract, not data |
| everything else | **denied** | Deny-by-default until identity lands |

**`/actuator/prometheus` is open to anything that can reach the port.** It is meant for a
scraper inside your deployment's network, and it exposes operational detail — request rates,
error counts, database pool state — that you should not hand to the public internet. Keep the
management port unreachable from outside, or put the path behind your reverse proxy. This is
the single most likely misconfiguration of a fresh install, so it is worth doing on day one.

Metrics export is enabled explicitly in `application.yml`. From Spring Boot 3.5 onwards it is
opt-in, and without that setting the scrape endpoint is never registered and quietly 404s.
