# Getting started

<p align="center">
  <img src="../assets/engine-overview.png" alt="Ludus at a glance: the project table with its single row, what the foundation already enforces, and what arrives in later releases" width="900">
</p>

What follows works today, on `main`. Anything not yet built is called out as such. The picture
above is the same claim in one frame: a green tick is something you can run now, and anything
marked *coming soon* is not in the box yet.

## Requirements

Docker, and nothing else. To build from source instead, JDK 21.

## Run it

```bash
git clone https://github.com/MiladNalbandi/ludus-engine.git
cd ludus-engine
cp deploy/.env.example deploy/.env
```

Open `deploy/.env` and change `LUDUS_DB_PASSWORD`. Compose refuses to start without it, on
purpose — a default database password in a public quickstart is a default database password in
production three months later.

```bash
docker compose -f deploy/docker-compose.yml up
```

First run builds the image, which takes a few minutes. After that it is seconds.

## Confirm it works

```bash
curl -s localhost:8080/actuator/health
# {"status":"UP", ...}
```

| | |
|---|---|
| API documentation | <http://localhost:8080/docs> |
| OpenAPI document | <http://localhost:8080/api-docs> |
| Health | <http://localhost:8080/actuator/health> |
| Metrics | <http://localhost:8080/actuator/prometheus> |

Everything else needs a credential:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/api/v1/anything
# 401
```

## Sign in

Set `LUDUS_JWT_SECRET` and the two administrator variables in `deploy/.env` before the first
start; the engine refuses to start without a signing secret, and without an administrator nobody
can sign in.

```bash
openssl rand -base64 48   # put this in LUDUS_JWT_SECRET
```

Then exchange the password for a pair of tokens:

```bash
curl -s localhost:8080/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"..."}'
```

```json
{
  "accessToken": "<a signed JWT>",
  "tokenType": "Bearer",
  "accessTokenExpiresAt": "2026-08-28T09:15:00Z",
  "refreshToken": "<an opaque random string>",
  "refreshTokenExpiresAt": "2026-09-27T09:00:00Z"
}
```

The two are different kinds of thing, which the placeholders say better than a sample would. The
access token is a signed JWT: anything holding the signing key can read the project and role out
of it and check it without asking the database. The refresh token is 256 random bits with no
structure at all — the engine keeps only a digest of it, so it is meaningless to anyone who has
the database and useful only to whoever was handed it.

The access token lasts fifteen minutes and cannot be revoked; the refresh token lasts thirty days
and can. Use the access token, and when it expires, exchange the refresh token at
`/api/v1/auth/refresh` for a new pair — which also revokes the one you presented.

```bash
curl -s localhost:8080/api/v1/me -H "Authorization: Bearer $ACCESS_TOKEN"
# {"kind":"USER","subject":"...","project":"...","role":"ADMIN"}
```

## A key for your game client

Game clients get an API key rather than a password. It is read-only, scoped to the project, shown
once, and revocable.

```bash
curl -s localhost:8080/api/v1/admin/api-keys \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"android-client"}'
```

The `key` field in that response is the only copy. Only a digest is stored, so nobody — including
whoever runs the database — can show it to you again. Clients send it as a header:

```bash
curl -s localhost:8080/api/v1/me -H "X-API-Key: ludus_..."
# {"kind":"API_KEY","subject":"...","project":"...","role":"VIEWER"}
```

## Build and test from source

```bash
./mvnw verify
```

That runs the unit tests, the JSON Schema conformance tests, the architecture rules and the
dependency bans. It takes well under a minute on a warm cache.

To run one module or one test:

```bash
./mvnw -pl engine/engine-domain test
./mvnw -Dtest=SlugTest test
```

## What you can't do yet

You can author content — create a wave, validate it, publish it — but **a game client cannot fetch
it yet**. There are no public routes, no `ETag`, and no status poll, so nothing outside the
authoring API can read a document. That is the rest of `v0.2.0`.

- The public routes and the caching protocol arrive in `v0.2.0` — [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8)
- The visual editor arrives in `v0.3.0` — [#9](https://github.com/MiladNalbandi/ludus-engine/issues/9)

What *does* exist and is worth looking at now: the [content contract](../concepts/content-model.md)
in `contracts/schemas/wave/v1.json`, and three worked examples in `samples/waves/` that are
validated against it on every build.

## Troubleshooting

**Compose exits immediately complaining about `LUDUS_DB_PASSWORD`.** You skipped editing
`deploy/.env`. That is the intended behaviour.

**The engine container restarts.** Almost always the database not being ready. Compose waits on a
health check, so this should be rare; if it persists, `docker compose -f deploy/docker-compose.yml logs engine`
will say why.

**`/actuator/prometheus` returns 404 rather than metrics.** Metrics export is opt-in from Spring
Boot 3.5 onwards and is enabled explicitly in `application.yml`. If you have overridden that
configuration, put it back.

**Port 8080 is taken.** Set `LUDUS_PORT` in `deploy/.env`.
