# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions before `1.0.0` do not promise a stable HTTP contract. The contract is frozen at
`1.0.0`; see the roadmap in the README.

## [Unreleased]

### Added

- Brand assets under `assets/brand/`: an **L** mark with a blue slash forming the leading edge
  of its foot, in light, dark and monochrome variants, plus horizontal lockups, favicons, an
  avatar and usage notes. The mark is solid geometry with no fine detail, so a single mark
  covers every size down to 16 px — `contact-sheet.png` shows it rasterised at real pixel sizes
  rather than asserting that it holds.
- The README header now shows the lockup, switching between the light and dark variants with
  the reader's colour scheme.

- Documentation set under `docs/`: an index, a getting-started guide, a deployment guide, and
  concept pages for the content model and for the caching / change-detection protocol. Pages
  mark planned behaviour explicitly and link to the issue tracking it, so nothing documented
  here describes something that does not work.
- `scripts/publish-wiki.sh` mirrors `docs/` into the GitHub Wiki for anyone who prefers reading
  it there. The repository remains the source of truth; the wiki is a published copy.
- A roadmap issue per phase, tracked in
  [#18](https://github.com/MiladNalbandi/ludus-engine/issues/18).

### Fixed

- Commits are now attributed to the maintainer's GitHub account. The initial history used an
  email address that is not verified on that account, so GitHub rendered the commits as an
  unlinked name with no avatar and did not count them as contributions.

## [0.0.1] - 2026-08-21

The foundation. Nothing to play with yet; everything to build on.

### Added

- Multi-module Maven build (Java 21, Spring Boot 3.5) split into domain, application, and
  persistence / web / security adapters, with a single composition root.
- Layering enforced two ways: `engine-domain` and `engine-application` declare no framework
  dependencies, so a Spring import into either fails the build at the enforcer; ArchUnit covers
  dependency direction, framework types in the inner layers, and field injection.
- The wave JSON Schema as the single source of truth at `contracts/schemas/wave/v1.json`,
  copied into the jar at build time, with a conformance test that validates every sample
  against it.
- Three CC0 demo waves.
- A deny-by-default baseline security chain. Only the health, info and metrics endpoints and
  the API documentation are reachable; everything else is denied until identity lands.
- `/actuator/health`, `/actuator/info`, `/actuator/prometheus`, and OpenAPI at `/api-docs`
  with Swagger UI at `/docs`.
- `docker compose up` quickstart with Postgres.
- CI running the full test suite, secret scanning and CodeQL on every push and pull request.
