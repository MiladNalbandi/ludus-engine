# WaveMaker

The Python service. A core that knows nothing about games, plus apps that are plugins.

The design, and the reasoning behind it, is in
[docs/architecture/platform.md](../docs/architecture/platform.md). This file only says how to run
what is here.

Nothing is implemented yet. This is the scaffold R0 builds on: the package layout, the test
command, and the three architecture walls written as checks.

## Run it

```bash
cd service
uv venv --python 3.12 .venv && . .venv/bin/activate
uv pip install -e ".[dev]"
```

| Command                       | What it does                                |
| ----------------------------- | ------------------------------------------- |
| `python -m pytest -q`         | Every test                                  |
| `python -m pytest -q -k AC-1` | Only the tests for one acceptance criterion |
| `python -m ruff check .`      | Lint                                        |
| `python -m mypy .`            | Types, in strict mode                       |
| `lint-imports`                | The three architecture walls                |

These are the commands keel runs, so they are the ones that must keep working.

## The layout

```
src/wavemaker/
  platform/      the core: identity, tenancy, http, events. No game words.
    kernel/      app manifests and the registry that loads them. No framework.
  apps/          one folder per plugin. Empty until R1.
tests/
  unit/          pure functions and classes, no I/O
  integration/   the database, the HTTP layer or the file system, for real
```

## The walls

Three rules from the design are checks rather than good intentions, in `pyproject.toml` under
`[tool.importlinter]`:

1. **The platform core knows nothing about any app.** The core must stand on its own, or an app
   can never be removed.
2. **Apps are independent of each other.** If inventory needs money it asks through a port or
   listens for an event. The first direct import between two apps is the moment the plugin model
   dies.
3. **A domain imports no framework.** The kernel may not import FastAPI, SQLAlchemy or uvicorn.

Each one was checked by breaking it on purpose and watching `lint-imports` report `BROKEN`. The
second rule needed the wildcard `wavemaker.apps.*` to work at all: written as `wavemaker.apps` it
passed happily while one app imported another, because a list of one module has nothing to be
independent of.
