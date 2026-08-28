# Ludus documentation

<p align="center">
  <img src="assets/engine-overview.png" alt="Ludus at a glance: the project table with its single row, what the foundation already enforces, and what arrives in later releases" width="900">
</p>

Ludus is a backend engine for 2D games. You author levels, entities and behaviour as **data**;
your game fetches that data at runtime and builds the level from it. Ship a balance change
without shipping a build.

It is not a game engine. It does not render, simulate physics, or run your game loop. Your
engine does that — Ludus tells it what to build.

> **Status: v0.0.1.** Be aware of what does and does not exist yet. This release is the
> foundation: the build, the architecture guardrails, the content contract and a running
> service. **There is no content API yet** — that arrives in v0.2.0. Pages below mark planned
> behaviour explicitly and link to the issue tracking it. Nothing here describes something that
> does not work.

## Start here

| | |
|---|---|
| [Getting started](guides/getting-started.md) | Run the engine locally and confirm it works |
| [Deployment](operations/deployment.md) | Running it somewhere real |
| [Configuration](operations/configuration.md) | Every environment variable, and which ones have security consequences |

## Concepts

| | |
|---|---|
| [The content model](concepts/content-model.md) | Documents, schemas, drafts and publication |
| [Caching and change detection](concepts/caching.md) | How clients know content changed, and why one hash backs two signals |

## Architecture

| | |
|---|---|
| [Overview](architecture/overview.md) | The pieces, the modules, and two ideas worth understanding early |
| [Hexagonal rules](architecture/hexagonal.md) | The layering, and how the build enforces it |
| [Decision records](architecture/adr/) | Why things are the way they are, including rejected options |

## Project

| | |
|---|---|
| [Roadmap](roadmap.md) | Where this is going and in what order |
| [Contributing](../CONTRIBUTING.md) | Build, test, and the rules a change has to respect |
| [Brand assets](../assets/brand/README.md) | The mark, the palette, and which variant to use at which size |
| [Security policy](../SECURITY.md) | Reporting a vulnerability |

## A note on these docs

They live in the repository rather than in a wiki, so a change to behaviour and the change to
its documentation land in the same commit and the same review. Documentation that can drift
silently from the code eventually does.

If you prefer reading them as a GitHub Wiki, `scripts/publish-wiki.sh` mirrors this directory
into one.
