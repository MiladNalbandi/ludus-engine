# Getting started

What follows works today, on `main`, and is what CI's Quickstart job runs on every change.

## Requirements

Docker, and nothing else. To run the service from source instead, Python 3.12 and
[uv](https://docs.astral.sh/uv/); the tests also need Docker, for a real PostgreSQL.

## Run it

```bash
git clone https://github.com/MiladNalbandi/ludus-engine.git
cd ludus-engine
cp deploy/.env.example deploy/.env
```

Open `deploy/.env` and set three things:

- `WAVEMAKER_DB_PASSWORD`. Compose refuses to start without it, on purpose: a default database
  password in a public quickstart is a default database password in production three months
  later. `openssl rand -hex 24` makes one that is safe inside a URL.
- `WAVEMAKER_JWT_SECRET`, from `openssl rand -base64 48`. The service refuses to start without a
  signing secret, and without one of at least 32 bytes.
- `WAVEMAKER_ADMIN_EMAIL` and `WAVEMAKER_ADMIN_PASSWORD`, the administrator to create on first
  start. Without one nobody can sign in.

```bash
docker compose -f deploy/docker-compose.yml up
```

The first run builds the service and editor images, which takes a few minutes. After that it is
seconds. The service migrates the database before it serves anything.

## Confirm it works

```bash
curl -s localhost:8080/health
# {"status":"ok","version":"0.1.0","apps":[{"name":"content","version":"1.0.0"}, ...]}
```

`apps` is every app that loaded: content, economy, inventory, leaderboard, media and progression
are built in, and installed plugins appear beside them.

| | |
|---|---|
| The editor | <http://localhost:3000> |
| API documentation | <http://localhost:8080/docs> |
| OpenAPI document | <http://localhost:8080/openapi.json> |
| Health | <http://localhost:8080/health> |

Authoring needs a credential:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/api/v1/admin/waves
# 401
```

## Sign in

Exchange the administrator's password for a pair of tokens:

```bash
curl -s localhost:8080/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"..."}'
```

```json
{
  "accessToken": "<a signed JWT>",
  "tokenType": "Bearer",
  "accessTokenExpiresAt": "2026-11-03T22:29:37.349189Z",
  "refreshToken": "<a signed JWT>",
  "refreshTokenExpiresAt": "2026-12-03T22:14:37.349189Z"
}
```

The access token lasts fifteen minutes and cannot be revoked; the refresh token lasts thirty days
and can, because only its digest is stored. Use the access token, and when it expires, exchange
the refresh token at `/api/v1/auth/refresh` for a new pair, which also revokes the one you
presented. The two carry different `typ` claims and neither is accepted where the other is
expected.

```bash
curl -s localhost:8080/api/v1/me -H "Authorization: Bearer $ACCESS_TOKEN"
# {"kind":"USER","subject":"...","project":"...","role":"ADMIN"}
```

## A key for your game, and a session for each player

A game build carries an API key rather than a password. It is shown once, only its digest is
stored, and it buys exactly one thing: a player session.

```bash
curl -s localhost:8080/api/v1/admin/api-keys \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"android-client"}'
# {"id":"...","name":"android-client","prefix":"wm_...","role":"VIEWER","createdAt":"...","key":"wm_..."}
```

The game exchanges it for a player session with its own identifier for the player:

```bash
curl -s localhost:8080/api/v1/public/players/session \
  -H "X-API-Key: wm_..." -H 'Content-Type: application/json' \
  -d '{"externalId":"device-0001"}'
# {"playerId":"...","externalId":"device-0001","displayName":null,"token":"...","expiresAt":"..."}
```

The session token lasts an hour and reaches that one player's state under `/api/v1/player/me`:
the wallet, the inventory, progress and leaderboard scores.

## What a game client reads

Published content needs no credential. It is what every copy of the game downloads, so a secret
that ships inside the binary would be one in name only.

```bash
curl -s localhost:8080/api/v1/public/status
# {"contentHash": "35ea7b2a8f7dbb07ecf4cb7a96375819"}
```

Compare that with the hash you cached. Unchanged means play from cache and make no further
requests. Changed means fetch the list, then the documents you need:

```bash
curl -si localhost:8080/api/v1/public/waves | grep -i '^etag'
# etag: "35ea7b2a8f7dbb07ecf4cb7a96375819"

curl -s localhost:8080/api/v1/public/waves/demo_first_steps/raw
# the document, byte for byte as it was authored
```

Send the ETag back and you get nothing, which is the point:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/api/v1/public/waves \
  -H 'If-None-Match: "35ea7b2a8f7dbb07ecf4cb7a96375819"'
# 304
```

Store the raw bytes and the ETag together; an ETag is only useful beside the bytes it validates.
The hash from `/status` and the ETag of `/waves` are the same value for the same data, on
purpose: two signals computed separately can disagree, and a client caught between them is very
hard to debug. The settings the game should launch with are at `/api/v1/public/app-config`,
`{}` until somebody sets them, cached the same way.

## Build and test from source

```bash
cd service
uv venv --python 3.12 .venv && . .venv/bin/activate
uv pip install -e ".[dev]"
python -m pytest -q     # every test, against a real PostgreSQL in a container
python -m ruff check .  # lint
python -m mypy .        # types, strict
lint-imports            # the architecture walls
```

`tests/integration/test_frozen_contract.py` is the one that walks the whole v1 contract. To run
the service against a database of your own:

```bash
export WAVEMAKER_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/wavemaker
export WAVEMAKER_JWT_SECRET="$(openssl rand -base64 48)"
export WAVEMAKER_ADMIN_EMAIL=you@example.com WAVEMAKER_ADMIN_PASSWORD=change-me
python -m uvicorn --factory wavemaker.platform.http.factory:create_app --port 8080
```

## Troubleshooting

**Compose exits immediately naming `WAVEMAKER_DB_PASSWORD` or `WAVEMAKER_JWT_SECRET`.** You
skipped editing `deploy/.env`. That is the intended behaviour.

**The service container restarts.** `docker compose -f deploy/docker-compose.yml logs service`
says why. The usual reasons are a signing secret under 32 bytes, an optional setting left as an
empty value rather than commented out, and a database password with a character that means
something in a URL.

**Mixing audio answers 503.** The standard image has no FFmpeg. See
[configuration](../operations/configuration.md#media).

**Port 8080 or 3000 is taken.** Set `WAVEMAKER_PORT` or `WAVEMAKER_EDITOR_PORT` in `deploy/.env`.
