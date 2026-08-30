# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions before `1.0.0` do not promise a stable HTTP contract. The contract is frozen at
`1.0.0`; see the roadmap in the README.

## [Unreleased]

### Added

- **Wave authoring** — the first half of `v0.2.0`,
  [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8). Documents can be created,
  validated, published and read back under `/api/v1/admin/waves`, by an `EDITOR` or above.
  - Documents are stored **verbatim** in a text column, with a generated `jsonb` column derived
    from it for indexing. Neither the write path nor the read path parses and re-serialises,
    because that moves the bytes — and the ETag is a hash of them, so every client would
    re-download the catalogue after a save that changed nothing.
  - Validation is against the published schema, in enforce mode, with errors reported at JSON
    Pointer paths so an editor can attach each one to the field that caused it. All violations are
    returned at once, not the first.
  - Saving never publishes. A new wave is a draft; publication is a separate call.
  - `progression_config.order` is derived from the document and never accepted as a request field.
    A collision is a `422` at `/progression_config/order`, backed by a unique index so two
    concurrent writes cannot both claim it.
  - `schema_version` is stamped when a document omits it. That is the one path in the engine
    allowed to change a document's bytes, and it has its own port and its own test.
- `ContentHashes` computes both the document ETag and the catalogue hash. The public routes that
  will serve them arrive in the second half of `v0.2.0`; the function exists now so the two signals
  cannot be implemented separately and disagree.
- `StatelessAuthenticationTest` asserts the invariant that makes disabling CSRF safe — no
  `UserDetailsService`, no session cookie, no Basic challenge. The four CodeQL alerts on the
  identity code are dismissed citing it.

### Changed

- `/api/v1/admin/waves/**` requires `EDITOR`; the rest of `/api/v1/admin/**` still requires
  `ADMIN`. Authoring content is what the editor role is for, and a leaked API key must still not be
  able to mint another key.
- Flyway now reads `classpath:db/migration` plus `classpath:db/vendor/{vendor}`. The generated
  `jsonb` column is PostgreSQL-only and lives in the vendor location, so the shared schema stays
  one schema. The vendor directory is a sibling of `db/migration` rather than nested inside it,
  because Flyway scans a location recursively and would otherwise hand PostgreSQL-only SQL to H2.
- `engine-application`'s enforcer now bans Jackson and networknt, matching `engine-domain` and the
  ArchUnit rule that already forbade importing them.

## [0.1.0] - 2026-08-30

Identity. Sign in, roles, and API keys for game clients, on top of the project boundary every
table has carried since the first migration. Still no content API.

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
