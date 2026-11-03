# Contributing to Ludus

Thanks for considering it. Bug reports with a reproduction are as valuable as patches.

## Getting set up

You need **Python 3.12** with [uv](https://docs.astral.sh/uv/), **Docker** (the tests run against
a real PostgreSQL in a container), and **Node 22** for the editor.

```bash
cd service
uv venv --python 3.12 .venv && . .venv/bin/activate
uv pip install -e ".[dev]"

python -m pytest -q                 # everything: unit, integration, the frozen contract
python -m pytest -q -k AC-1         # the tests for one acceptance criterion
python -m pytest -q tests/unit      # one directory
python -m ruff check .              # lint
python -m mypy .                    # types, strict
lint-imports                        # the architecture walls
```

```bash
cd editor
npm ci
npm run typecheck && npm run lint && npm test && npm run verify:types
```

`docker compose -f deploy/docker-compose.yml up` runs the whole stack locally, exactly as CI's
Quickstart job does.

## The architecture rules

The service is a modular monolith of hexagonal apps, and the walls are enforced by
`lint-imports`, so a violation shows up as a failing build rather than as review feedback:

- **The platform core knows nothing about any app.** `wavemaker.platform` may not import
  `wavemaker.apps`. The core must stand on its own, or an app can never be removed.
- **Apps are independent of each other.** If inventory needs money it asks through a port or
  listens for an event. The first direct import between two apps is the moment the plugin model
  stops being true.
- **The kernel imports no framework.** `wavemaker.platform.kernel` may not import FastAPI,
  SQLAlchemy or uvicorn.

Inside an app, `domain` holds the rules and knows nothing about HTTP or PostgreSQL, `application`
holds the ports, and `adapters` connect them to the outside.

**The v1 HTTP contract is frozen.** `docs/api/openapi-v1.json` does not change, and
`service/tests/integration/test_frozen_contract.py` fails when a change takes away something a
client depends on. Adding is fine; removing costs a major version.

If a rule fires and you believe it is wrong, say so in the pull request — the rules are a design
decision and can be revised. Please do not add a suppression instead.

See [docs/architecture/platform.md](docs/architecture/platform.md) for the reasoning.

## Commits and pull requests

- **[Conventional Commits](https://www.conventionalcommits.org/)** for the title, e.g.
  `feat(content): serve published waves with an ETag`. The release notes are generated from
  them.
- Explain **why** in the body. What changed is visible in the diff; the reasoning is not.
- One logical change per pull request.
- New behaviour comes with a test. A bug fix comes with a test that fails without the fix.
- A written migration is never edited. Add a new one.
- Update `CHANGELOG.md` under `## [Unreleased]`.

## Contributor Licence Agreement

Pull requests require signing a CLA, which is automated — a bot comments on your first pull
request with a link, and it takes a minute.

Being direct about why, because a CLA is friction and you deserve a real reason: Ludus is
AGPL-3.0 today, and the intention is a hosted service alongside the open-source project. A CLA
keeps relicensing and dual-licensing possible; without one, the project could never offer a
commercial tier containing community contributions, and could not fix a licensing mistake
later without tracking down every contributor. This is the same arrangement Grafana uses. The
CLA does **not** take your copyright away — you keep it, and you grant the project a licence.

## Reporting security issues

Please do not open a public issue. See [SECURITY.md](SECURITY.md).
