# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions before `1.0.0` do not promise a stable HTTP contract. The contract is frozen at
`1.0.0`; see the roadmap in the README.

## [Unreleased]

### Added

- **Identity** — `v0.1.0`, [#7](https://github.com/MiladNalbandi/ludus-engine/issues/7). Users,
  roles, signing in, and API keys for game clients.
  - `POST /api/v1/auth/token` exchanges an email address and password for an access token and a
    refresh token. `POST /api/v1/auth/refresh` exchanges the refresh token for a new pair and
    revokes the one presented, so a stolen token and the real one cannot both keep working.
    `GET /api/v1/me` reports the identity behind whatever credential was sent.
  - Three roles — `VIEWER`, `EDITOR`, `ADMIN` — checked in one filter chain rather than per
    controller, with a table-driven test stating the whole policy in one file.
  - API keys for game clients, under `POST /api/v1/admin/api-keys`. Shown once, stored as a
    digest, scoped to a project, always read-only, and revoked by stamping rather than deleting.
  - Passwords are stored with BCrypt; machine-generated secrets with SHA-256, which is
    deterministic so a presented credential is one indexed lookup rather than a scan.
  - Every authentication failure returns the same 401 with the same body. Telling an unknown
    address apart from a wrong password turns a login form into a list of who has an account.
  - The first administrator is seeded from `LUDUS_ADMIN_EMAIL` / `LUDUS_ADMIN_PASSWORD`, only
    into a project that has no users. It never resets an existing administrator's password.

- The project boundary, and the first migration. `V1__project.sql` creates the `project` table
  that every later table refers to. A `single`-tenant install provisions one project on first
  start, under the slug `default`; the check is idempotent, so a restart finds it rather than
  adding another. Part of `v0.1.0` —
  [#7](https://github.com/MiladNalbandi/ludus-engine/issues/7).
- `engine-application` and `engine-adapter-persistence` have code in them for the first time: an
  outbound port, a use case with no framework types and a plain-JUnit test against a hand-written
  repository, and a JPA adapter behind it.

- Brand assets under `assets/brand/`: an **L** mark with a blue slash forming the leading edge
  of its foot, in light, dark and monochrome variants, plus horizontal lockups, favicons, an
  avatar and usage notes. The mark is solid geometry with no fine detail, so a single mark
  covers every size down to 16 px — `contact-sheet.png` shows it rasterised at real pixel sizes
  rather than asserting that it holds.
- The README header now shows the lockup, switching between the light and dark variants with
  the reader's colour scheme.
- The project illustration, as `assets/brand/hero.png` and `assets/brand/hero-illustration.png`.
  The README header uses the cropped illustration above the lockup; the wordmark is left to the
  lockup, which is the variant that survives a dark background. `assets/brand/hero-card.png` is
  the same composition as a finished card, for social previews and slides.
- `docs/assets/engine-overview.png`, a figure showing what the engine does and does not do yet,
  on the documentation index, the getting-started guide and the roadmap. `publish-wiki.sh` now
  rewrites image paths to raw URLs, because the wiki's namespace is flat and carries no assets.

- Documentation set under `docs/`: an index, a getting-started guide, a deployment guide, and
  concept pages for the content model and for the caching / change-detection protocol. Pages
  mark planned behaviour explicitly and link to the issue tracking it, so nothing documented
  here describes something that does not work.
- Slice tests run the shipped migrations against H2 in PostgreSQL mode with Hibernate's schema
  validation on, so an entity that has drifted from its migration fails the build rather than the
  deploy. The identity tests run with two projects present throughout, because a repository that
  ignores its project argument passes every single-project test ever written.

- `scripts/publish-wiki.sh` mirrors `docs/` into the GitHub Wiki for anyone who prefers reading
  it there. The repository remains the source of truth; the wiki is a published copy.
- A roadmap issue per phase, tracked in
  [#18](https://github.com/MiladNalbandi/ludus-engine/issues/18).

### Changed

- **`LUDUS_JWT_SECRET` is required and has no default.** The engine refuses to start without
  one, and refuses anything shorter than 32 bytes. A signing secret published in a public
  repository is a working forgery tool for every install that kept it.
- **An unauthenticated request now returns `401` rather than `403`.** It said `403` while
  nobody could ever be allowed, which was the whole truth at the time. A caller who is signed in
  and merely lacks the role still gets `403`, and the two send whoever is debugging to different
  places.
- The single deny-all filter chain is replaced by the three ordered chains its own comment
  described: operational endpoints, documentation, and the API.

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
