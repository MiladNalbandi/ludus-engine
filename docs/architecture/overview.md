# Architecture overview

WaveMaker is one Python service and one PostgreSQL database. No message broker, no second
backend, no orchestrator required. That is a deliberate ceiling on operational cost: someone
should be able to run this on a small VM for a game that is not yet successful, and the design
should not punish them for it.

## The pieces

| | |
|---|---|
| **Service** | Python 3.12 / FastAPI, in `service/`. Owns content, validation, publication and player state. |
| **Editor** | Next.js, in `editor/`. A shell plus one module per app, talking to the service through its own server. |
| **Your game** | Reads published content over HTTP and writes player state back. |
| **PostgreSQL** | The only datastore. Migrated by the service at startup, with Alembic. |

## Inside the service

```
service/src/wavemaker/
  platform/        the core: identity, tenancy, http, persistence, storage, plugins
    kernel/        manifests and the registry that loads them. No framework.
  apps/            one folder per app, each with a manifest.toml
    content/       waves, levels, application configuration
    economy/       wallets and currency
    inventory/     items and what players hold
    leaderboard/   boards and scores
    progression/   the XP curve and rewards
    media/         audio and sprites
```

A **modular monolith**: one process, with walls between the parts. The core knows nothing about
games. Each app is a plugin the core loads from its manifest without knowing what is in it, which
is what lets an app leave this repository as a package and come back through `plugin install`.

Each app is **hexagonal**: `domain` holds the rules and imports no framework, `application`
holds the ports, and `adapters` connect them to FastAPI and PostgreSQL. Three walls are checks
rather than conventions, enforced by `lint-imports` on every build: the core imports no app, no
app imports another, and the kernel imports no framework. The reasoning is in
[platform.md](platform.md); the checks are in `service/pyproject.toml`.

## Two ideas worth understanding early

**Content is documents, not columns.** A wave is a JSON document validated against a published
JSON Schema. The database indexes what it needs to query (identifier, name, order, publication
state) and stores the document itself verbatim. The schema, not a class in the service, is the
contract. That is what lets the content model grow without a migration every time a behaviour
gains a parameter, and what lets the editor and the game client agree on a shape without either
importing the other's code.

**Publication is separate from saving.** Editing content never affects players. Only published
content is served on the public routes, and to an unauthenticated client a draft is
indistinguishable from something that does not exist. The alternative is that saving a
half-finished level ships it to everyone playing.

## Caching

Public content is cacheable and validated by ETag. The digest that produces those ETags is the
same function that produces the content hash a client polls to decide whether to refetch —
deliberately the same, because if the two are computed differently a client can be told
"something changed" by one signal while an HTTP cache serves it bytes validated by the other,
and the bug that produces is very hard to see.
