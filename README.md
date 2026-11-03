<p align="center">
  <img src="assets/brand/hero-illustration.png" alt="" width="560">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-horizontal-dark.png">
    <img src="assets/brand/logo-horizontal.png" alt="Ludus" width="380">
  </picture>
</p>

<p align="center">
  <strong>An open-source backend engine for 2D games.</strong><br>
  Author your maps, entities and behaviours as data in a web editor; your game fetches them at
  runtime and builds the level from them. Ship a balance change without shipping a build.
</p>

<p align="center">
  <a href="https://github.com/miladnalbandi/ludus-engine/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/miladnalbandi/ludus-engine/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="Licence: AGPL v3" src="https://img.shields.io/badge/licence-AGPL--3.0-blue.svg"></a>
  <a href="https://github.com/miladnalbandi/ludus-engine/issues/18"><img alt="Roadmap" src="https://img.shields.io/badge/roadmap-%2318-5B4FE9"></a>
</p>

> **Status: moving to Python.** Ludus is being rebuilt as **WaveMaker**, a modular game backend in
> Python and FastAPI where every feature is a plugin you can publish and install. The Python service
> already serves and authors content, signs people in, and runs the web editor unchanged. The
> Java `v1.0.0` engine stays in this repository as the reference the rewrite is checked against,
> until every v1 contract test passes on Python ([#77](https://github.com/MiladNalbandi/ludus-engine/issues/77)).

## What it is, and what it is not

Ludus is the **backend** for a 2D game. It owns the content your game reads and the player
state your game writes: levels and maps, entity definitions, behaviour parameters, and later
XP, items, currency, inventory and notifications. It gives you a web editor to author all of
that, and an HTTP API your game client reads it from.

Ludus is **not** a game engine. It does not render, simulate physics, or run your game loop.
Your engine does that. Ludus tells it what to build.

## Quickstart

```bash
git clone https://github.com/miladnalbandi/ludus-engine.git
cd ludus-engine
cp deploy/.env.example deploy/.env
# Set LUDUS_JWT_SECRET (openssl rand -base64 48) and the two LUDUS_ADMIN_* values.
# The engine refuses to start without a signing secret, deliberately.
docker compose -f deploy/docker-compose.yml up
```

That starts the Java `v1.0.0` engine, which is still the one the Quickstart deploys. Then open:

| | |
|---|---|
| API documentation | http://localhost:8080/docs |
| OpenAPI document | http://localhost:8080/api-docs |
| Health | http://localhost:8080/actuator/health |

### The Python service

You need Python 3.12 and Docker — the tests run against a real PostgreSQL in a container.

```bash
cd service
uv venv --python 3.12 .venv && . .venv/bin/activate
uv pip install -e ".[dev]"
python -m pytest -q        # 179 tests
lint-imports               # the architecture walls
```

Run it against a database:

```bash
export WAVEMAKER_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/wavemaker
export WAVEMAKER_JWT_SECRET="$(openssl rand -base64 48)"
export WAVEMAKER_ADMIN_EMAIL=you@example.com WAVEMAKER_ADMIN_PASSWORD=change-me
python -m uvicorn --factory wavemaker.platform.http.factory:create_app --port 8080
```

It migrates the database and creates the first administrator on start, and refuses to start
without a signing key of at least 32 bytes. See [service/README.md](service/README.md).

To build and test the Java engine you need JDK 21: `./mvnw verify`.

## Architecture

```
   ┌────────────────┐     authoring      ┌──────────────────────────────────┐
   │     editor     │ ─────────────────▶ │            WaveMaker             │
   │ (Next.js, TS)  │                    │       (Python, FastAPI)          │
   └────────────────┘                    │                                  │
                                         │  core   identity · tenancy ·     │
   ┌────────────────┐  content + player  │         http · plugin loader     │
   │   your game    │ ◀────────────────▶ │  apps   [content] [economy] …    │
   │ (Unity, Godot) │       state        │         each one a plugin        │
   └────────────────┘                    └────────────────┬─────────────────┘
                                                          │
                                                     PostgreSQL
```

A **modular monolith**: one service to run, with real walls between the parts. The core knows
nothing about games. Each app is a folder with a `manifest.toml`, and the core loads it without
knowing what is in it — which is what lets an app later leave this repository as a package and
come back through `plugin install`.

Each app is **hexagonal** (ports and adapters): the game rules sit in the middle and know nothing
about FastAPI or PostgreSQL. The walls are checks, not conventions — `lint-imports` fails the build
when:

- the core imports an app,
- one app imports another, or
- the kernel imports a framework.

Each was tested by breaking it on purpose. The design, and the reasoning behind every choice, is in
[docs/architecture/platform.md](docs/architecture/platform.md).

The Java engine (`engine/`) is hexagonal too, enforced by the Maven enforcer and ArchUnit. See
[docs/architecture/hexagonal.md](docs/architecture/hexagonal.md).

| | Python service | Java reference |
|---|---|---|
| Language | Python 3.12 | Java 21 |
| Web | FastAPI | Spring Boot |
| Database | PostgreSQL 16, SQLAlchemy, Alembic | PostgreSQL 16, Flyway |
| Auth | PyJWT, Argon2id | Spring Security |
| Tests | pytest, Testcontainers | JUnit, ArchUnit |
| Architecture checks | import-linter | Maven enforcer, ArchUnit |
| Lint and types | ruff, mypy `--strict` | — |

## The content contract

Content is JSON, validated against a JSON Schema that lives in exactly one place —
[`contracts/schemas/wave/v1.json`](contracts/schemas/wave/v1.json) — and is shared by the
engine, the editor and every client. There is no second copy to drift.

`samples/waves/` holds three worked examples, and they are validated against that schema on
every build. If a sample and the contract disagree, CI fails.

## Roadmap

### WaveMaker — the Python platform

Each release is a working service, and the frozen HTTP contract does not change during the
rewrite: if the contract tests pass, the Python is correct.

| | Release | |
|---|---|---|
| ✅ | R0 | The core boots, loads apps, and refuses the ones that must not run |
| ✅ | R1 | Content read side, on PostgreSQL, with ETag caching |
| ✅ | R2 | Identity, and authoring — **the editor runs on Python unchanged** |
| 📋 | [R2c](https://github.com/MiladNalbandi/ludus-engine/issues/70) | Level authoring routes |
| 📋 | [R3](https://github.com/MiladNalbandi/ludus-engine/issues/71) | Players and economy |
| 📋 | [R4](https://github.com/MiladNalbandi/ludus-engine/issues/72) | Inventory, the first app built plugin-first |
| 📋 | [R5](https://github.com/MiladNalbandi/ludus-engine/issues/73) | **Publish and install a plugin** — the release that makes this a platform |
| 📋 | [R6](https://github.com/MiladNalbandi/ludus-engine/issues/74) | Leaderboards and progression |
| 📋 | [R7](https://github.com/MiladNalbandi/ludus-engine/issues/75) | Media: audio and sprites |
| 📋 | [R8](https://github.com/MiladNalbandi/ludus-engine/issues/76) | The editor as a shell plus app modules |
| 📋 | [R9](https://github.com/MiladNalbandi/ludus-engine/issues/77) | Remove the Java |

### The Java engine, `v1.x`

Tracked in [#18](https://github.com/MiladNalbandi/ludus-engine/issues/18). These releases shipped in
Java; the features from `v1.1.0` on are now planned as WaveMaker apps instead.

| | Release | |
|---|---|---|
| ✅ | `v0.0.1` | Foundation: build, architecture guardrails, content contract, running service |
| ✅ | `v0.1.0` | Identity: JWT, roles, API keys, the project boundary |
| ✅ | `v0.2.0` | Content API: author, validate, publish and serve waves and levels, with ETag caching |
| ✅ | `v0.3.0` | The web editor: timeline, live preview, audio, level sequencer |
| ✅ | `v0.4.0` | Live-ops: players, items, XP, currency, inventory, leaderboards |
| ✅ | `v1.0.0` | **Frozen HTTP contract**, docs, semantic-versioning commitment |
| 🚧 | `v1.1.0` | Plugin substrate: entity, behaviour and content types become data |
| 📋 | `v1.2.0` | Schema-driven editor, pluggable preview |
| 📋 | `v1.3.0` | Maps and blocks: the tilemap content type |
| 📋 | `v1.4.0` | Notification centre: templates, player segments, scheduling |
| 📋 | `v1.5.0` | Game client SDK (separate repository, Apache-2.0) |
| 📋 | `v2.0.0` | Multi-tenancy and hosted deployment |

## Game client SDK

Not built yet — it lands with `v1.5.0` in a separate repository so that Unity can install it
by git URL and version it independently. It will be **Apache-2.0**, not AGPL: see Licensing.

## The API contract

The HTTP contract is committed at [`docs/api/openapi.json`](docs/api/openapi.json) and is **frozen
from `1.0.0`**: a breaking change costs a major version, and `FrozenContractTest` fails the build if
one lands without it. See [upgrading](docs/operations/upgrading.md) for what counts as breaking.

Swagger UI is at `/docs` on a running engine, and the raw document at `/api-docs`.

## Documentation

**[Start at the documentation index](docs/README.md)**, or jump straight to:

- [Getting started](docs/guides/getting-started.md) — run it locally and confirm it works
- [The content model](docs/concepts/content-model.md) — documents, schemas, drafts and publication
- [Caching and change detection](docs/concepts/caching.md) — how clients know content changed
- [Architecture overview](docs/architecture/overview.md) and the
  [hexagonal rules](docs/architecture/hexagonal.md) that the build enforces
- [Deployment](docs/operations/deployment.md) and the
  [configuration reference](docs/operations/configuration.md)
- [Decision records](docs/architecture/adr/) — including options that were rejected, and why

The docs live in the repository rather than in a wiki, so a behaviour change and its
documentation land in the same commit and the same review. If you prefer a wiki,
`scripts/publish-wiki.sh` mirrors `docs/` into one.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and reproductions are as welcome as
patches. Discussions are open for questions and ideas.

## Licensing

| Part | Licence | Why |
|---|---|---|
| Engine and editor | **AGPL-3.0-or-later** | Improvements to the server come back to everyone |
| `contracts/` | Apache-2.0 | Speaking a protocol should not require a licence |
| `sdk/` (client SDKs) | Apache-2.0 | Linking a client into your game must not affect your game |
| `samples/` | CC0-1.0 | Copy them |

In plain terms: **you can run Ludus for free, for any game, commercial or not.** Making a game
with it puts no licence obligation on your game. The AGPL only asks something of you if you
offer *Ludus itself* to others as a hosted service — then you publish your modifications to
Ludus. The client SDK is Apache-2.0 precisely so that shipping it inside your game is
unencumbered.
