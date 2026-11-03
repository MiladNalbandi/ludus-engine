# WaveMaker: a modular game backend

**Status: built.** R0 to R9 are done: the service in `service/` serves the whole v1 contract, and
the Java engine was removed in R9 ([docs/platform/r9.md](../platform/r9.md)). This document was
the design agreed before the code was written, and is kept as the reasoning behind it.

## What we are building

One backend platform for games. You turn features on per game, like plugins. A small indie game
switches on two of them. A big game switches on all of them and later moves the fast parts to
another language.

Three names appear in this document, and they are three different things:

| Name                   | What it is                                                           | Where it goes                                        |
| ---------------------- | -------------------------------------------------------------------- | ---------------------------------------------------- |
| **WaveMaker**          | The platform. The core plus the apps.                                | New, in `service/`                                   |
| **Ludus**              | Today's backend: waves, levels, players, money, items. Java, v1.0.0. | Becomes apps inside WaveMaker                        |
| **Light Wave Maker**   | Your Next.js wave editor.                                            | Becomes the front-end module of the content app      |
| **Nightfall District** | Your Godot zombie game.                                              | A client. It uses the platform, it is not part of it |

## The shape

```
     Nightfall District        Light Attack          any future game
            |                       |                       |
            +-----------+-----------+-----------+-----------+
                        |  HTTP (and websocket later)
        +---------------v-----------------------------------+
        |                  WaveMaker                        |
        |                                                   |
        |  core      identity · tenancy · http · events     |
        |            (knows nothing about games)            |
        |  -----------------------------------------------  |
        |  apps      [content] [economy] [inventory]        |
        |            [leaderboard] [progression] [media]    |
        |            [matchmaking]            <- plugins    |
        +---------------+-----------------------------------+
                        |
                 PostgreSQL + file storage
```

An **app** is a plugin. It is one folder. You can switch it off and the rest still runs.

## The architecture I recommend

**A modular monolith, with hexagonal apps inside it.**

Three words to define first, because the rest of the document uses them.

**Modular monolith** — one program you start, with many modules inside, and real walls between the
modules. It is not microservices. Microservices means many small programs, each deployed on its
own.

**Hexagonal** (also called _ports and adapters_) — the business rules sit in the middle. The middle
knows nothing about FastAPI or PostgreSQL. Everything outside talks to the middle through small
interfaces, called **ports**. The code that connects a port to a real tool is an **adapter**.

```
          HTTP request                       PostgreSQL
               |                                  ^
          +----v----+                        +----|----+
          | adapter |                        | adapter |
          +----+----+                        +----^----+
               |  port (an interface)             |  port
          +----v----------------------------------+----+
          |            application: use cases          |
          |            domain: the game rules          |   <- no framework here
          +--------------------------------------------+
```

**DDD** (domain-driven design) — name the code after the words of the game. `Wave`, `Player`,
`ItemStack`. Keep each rule next to the data it protects, not in a service class far away.

### Why a modular monolith and not microservices

You asked for indie to AAA. These pull in opposite directions, and the monolith is the only one
that can do both.

|                          | Modular monolith                    | Microservices now                    |
| ------------------------ | ----------------------------------- | ------------------------------------ |
| Deploy for a small game  | One container                       | Eight containers, a queue, a gateway |
| Cost to start            | Low                                 | High, before you have any players    |
| A call between modules   | A function call                     | A network call that can fail         |
| Split one part out later | Possible, the wall is already there | Already done                         |

The walls are what matter. If modules only talk through ports, pulling one out later is a small job.
If they share database tables, it is never possible. So: **walls now, separate programs only when a
real load makes you.**

This is the same reasoning that gives you the C++ door later. See _The speed path_ below.

### Why not keep Java

Nothing is wrong with the Java. It works and it has 481 tests. The honest trade:

- **You lose** a frozen, tested, released v1.0.0. That is real and it is not small.
- **You gain** one language across the platform, much faster feature work, and a plugin model that
  the Java modules were never shaped for.

Because the loss is real, the plan keeps the Java running until Python passes the same tests. See
_Releases_.

## On disk

```
ludus-engine/
  editor/                  today's Next.js editor
  service/                 NEW: the Python platform
    platform/              the core. No game words in here.
      kernel/              app registry, config, the plugin loader
      identity/            accounts, API keys, player session tokens
      tenancy/             project / game isolation
      persistence/         database session, migration runner
      events/              the event bus port
      http/                FastAPI factory, error shape, OpenAPI
    apps/                  the plugins
      content/             waves + levels          (Ludus today)
      economy/             wallet, currency
      inventory/           items a player owns
      leaderboard/         scores
      progression/         levels, unlocks
      media/               audio + sprites
      matchmaking/         later
    sdk/                   generated client
  docs/
```

Every app has the same shape:

```
apps/inventory/
  domain/           pure Python. Item, Stack, the rules. No imports from FastAPI.
  application/      use cases, and the ports they need
  adapters/
    http/           the FastAPI router
    db/             the SQLAlchemy repository
  migrations/       this app's tables only
  ui/               optional front-end module
  manifest.py       what this app is
  tests/
```

The manifest is how the core finds an app. Nothing is wired by hand:

```python
APP = AppManifest(
    name="inventory",
    version="1.0.0",
    requires=["identity", "tenancy"],
    router=router,                       # mounted at /api/v1/inventory
    migrations="migrations",
    publishes=["inventory.item_granted"],
    subscribes=["economy.purchase_completed"],
    ui=UiModule(mount="/apps/inventory"),
)
```

**The rule that keeps the walls up:** an app may import `platform.*` and its own folder. It may
**not** import another app. If inventory needs money, it asks through a port or listens for an
event. A test fails the build when an app breaks this. The Java project already does this with
ArchUnit; Python gets the same check with `import-linter`.

## The front end is modular too

Today the editor is one Next.js app. It becomes a shell plus modules, one per backend app:

```
editor shell            login, project picker, navigation
  + content module      <- Light Wave Maker lives here
  + inventory module
  + economy module
```

A module ships with its app. Switch the app off and its screen disappears. Light Wave Maker is not
rewritten — it is moved in as the content module, and its wave JSON stays the format it is now.

## Plugins you can publish and install

An app is not only a folder in this repository. It is a **package you can release**, and another
installation can download and install it. You build a map editor for a 2.5D game once, publish it,
and any game on the platform installs it.

```
  you build it            you publish it           a game installs it
  apps/map-editor/   ->   map-editor-1.2.0    ->   wavemaker plugin install
                          (backend + ui +           map-editor@1.2.0
                           migrations)                      |
                                                            v
                                                    new tables, new routes,
                                                    new screen in the editor
```

**One plugin is one package.** It carries everything it needs, so installing it is one step:

```
map-editor-1.2.0/
  manifest.toml      name, version, what platform it needs, what it may do
  backend/           the Python app: domain, application, adapters
  migrations/        its own tables
  ui/                its screen for the editor, already built
```

**Versions are a promise.** The platform has its own API version, and a plugin says what it works
with. The core refuses a plugin that does not fit, instead of crashing later:

```toml
[plugin]
name = "map-editor"
version = "1.2.0"
requires_platform = ">=1.2,<2"
requires_plugins = ["content>=1.0"]
```

**A plugin says what it is allowed to do.** It does not get the whole machine. It asks, the core
grants, and the core enforces:

```toml
[permissions]
tables  = "own"                    # only tables with its own prefix
routes  = ["/api/v1/map-editor"]   # it cannot answer on another app's path
events  = { publish = ["map.saved"], subscribe = ["content.wave_published"] }
storage = { blobs = true, quota_mb = 500 }
outbound_http = false              # it cannot call the internet
```

**Safety, honestly.** An installed plugin is code someone else wrote, running in your service. That
is the real risk in this design, and I am not going to pretend otherwise. The plan handles it in
three steps, in this order:

1. **Your own plugins only.** At first the registry holds packages you publish and sign. Install
   checks the signature. This is enough while you are the only author.
2. **Review before listing.** When other people publish, a plugin is read before it is listed, the
   way an app store works.
3. **Separate process.** When untrusted plugins really matter, a plugin runs as its own small
   process and talks over the same ports. Slower, but it cannot read what it does not own.

Step 3 is also the same door as _The speed path_ below. A plugin out of process can be written in
any language, so a C++ map baker is just a plugin that happens not to be Python.

**The registry** starts as the simplest thing that works: a plugin is a signed archive, and the
index is a file listing names, versions and checksums. A real server comes only when there are
enough plugins to need searching. The install command is the same either way.

## Data and tenancy

One PostgreSQL database. Each app owns its own tables and never reads another app's tables.
Every table keeps `project_id`, exactly as the Java does today, so one deployment can serve
Nightfall District and Light Attack without them seeing each other.

Where it is useful, content stays stored as **the exact bytes that were sent**, with a generated
`jsonb` column next to it for queries. This is what makes the ETag caching correct today, and it is
worth keeping.

## The speed path, for later

Python is fast enough to decide things. It is not the right tool for 60 updates a second.

```
     control plane (Python)              data plane (C++ / Rust, later)
     what is true:                       what happens right now:
     who owns this item                  positions, hits, matchmaking ticks
     what a wave contains                a live session
     what the price is
                |                                   |
                +------------ events / gRPC --------+
```

The realtime service is **not** in the plan yet. The plan only keeps its door open: session and
matchmaking sit behind ports from day one, so the thing behind them can be replaced without
touching the apps.

## Releases

Each release is a working service. Nothing is deleted until its replacement passes.

| R      | What ships                                                    | Done when                                                                                   |
| ------ | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **R0** | Core: config, tenancy, identity, plugin loader, one empty app | The service boots, loads apps, `/health` is green                                           |
| **R1** | `content` read side                                           | The same OpenAPI as Java v1. The existing editor and SDK work against Python with no change |
| **R2** | `content` write side                                          | Authoring, validation, publishing. Java content no longer needed                            |
| **R3** | `identity` players + `economy`                                | Player tokens, wallet. Same concurrency tests as Java                                       |
| **R4** | `inventory`                                                   | New app, built plugin-first                                                                 |
| **R5** | Publish and install                                           | `inventory` is packaged, signed, installed from the registry into a clean service           |
| **R6** | `leaderboard` + `progression`                                 | Keyset paging, same guarantee as today                                                      |
| **R7** | `media`                                                       | Audio and sprites, streamed                                                                 |
| **R8** | Editor shell + Light Wave Maker as a module                   | One editor, modules per app                                                                 |
| **R9** | Java removed                                                  | Every v1 contract test passes on Python                                                     |

**The contract does not change.** R1 to R7 answer the same HTTP contract that was frozen at v1.0.0,
checked by the same frozen-contract test. That is what makes the rewrite provable instead of
hopeful: if the test passes, the Python is correct.

**R5 is the one that proves the vision.** Everything before it could be a normal modular backend.
R5 is where a plugin leaves the repository, is published, and comes back by install — and the test
is exactly that: a service with no `inventory` folder installs the package and serves inventory.
A map-editor plugin for a 2.5D game is then the same path, with none of the platform changed.

Matchmaking and the realtime service come after R9, each with its own design.

## How the work runs

Through keel v2, with Opus on medium effort.

```
initiative   "WaveMaker platform"
   └── epic        one per release (R0 … R9)
         └── ticket     one per acceptance criterion
               └── keel flow   spec → criteria → RED test → GREEN code → review → ship
```

Each ticket is a keel flow. Each flow writes its own document, and the cost and token count of each
flow is recorded in `docs/platform/flow-log.md`, which is updated as the flows finish.

## What I would not do

- **Do not delete the Java early.** It is the only proof the Python is right.
- **Do not start with microservices.** You do not have the load, and the walls give you the split later.
- **Do not change the HTTP contract during the rewrite.** One hard thing at a time. Design v2 of the
  API after the rewrite, as a normal piece of work.
- **Do not write the C++ service yet.** Keep the port, build the thing when a real frame budget asks
  for it.
