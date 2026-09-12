# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions before `1.0.0` do not promise a stable HTTP contract. The contract is frozen at
`1.0.0`; see the roadmap in the README.

## [Unreleased]

### Added

- **Players, and the credential live-ops actually needs** — the foundation of `v0.4.0`,
  [#10](https://github.com/MiladNalbandi/ludus-engine/issues/10).
  - **The issue asks that "a game client can read and write player state with an API key". It
    cannot, and this is where that is resolved rather than quietly implemented.** An API key is
    `VIEWER`-only by explicit design, because it ships inside a binary anybody can unpack — so
    letting one write player state would let anyone who unpacked the game write *any* player's
    balance, inventory and scores. That is not a stricter reading of the requirement; it is the
    requirement being impossible as stated.
  - So the key keeps the job it is good at — which project, which build, and revocable — and it
    buys a **player session token**: an hour long, scoped to exactly one player, and the only
    credential that can write that player's state. A leaked key then lets an attacker play as a
    player of their own, which is unavoidable for anything shipped to a client, and lets them touch
    nobody else's.
  - **Every player route is `/me`**, and that is the security design rather than a naming style. A
    route shaped `/players/{id}` authorised by "is a player" is one where any player can act as any
    other, guarded only by a check somebody has to remember in each handler. With no id in the path
    there is nothing to forget.
  - **The two token kinds are not interchangeable**, and now structurally so. Both are signed with
    the same secret, so a `typ` claim is stamped and required on each side. Previously a player
    token failed admin verification only because it had no `role` claim and `Role.fromString(null)`
    throws — accidental safety that stops being safe the first time somebody gives the role a
    sensible default.
  - **The chain's deny-by-default now requires a real role, not merely authentication.** With
    `authenticated()`, a player session token would have reached every API route nobody had thought
    to name. Authenticated is not the same question as authorised, and that fallback is where the
    two diverge.
  - A player is created on first sight, idempotently by a unique index on
    `(project_id, external_id)`: a client retrying through a network blip resolves the player it
    already has rather than stranding the first one's progress.
  - The engine holds no account — no email address, no password, no date of birth. It stores the
    identifier the game already has and treats it as opaque. The game vouches for it, which means a
    game with no server of its own gets device-level trust; that is stated rather than implied to be
    more.

- **The end-to-end journey, in a real browser** — completing `v0.3.0`,
  [#9](https://github.com/MiladNalbandi/ludus-engine/issues/9). `editor/e2e/journey.spec.ts` signs
  in, opens a wave, adds a movement, scrubs the preview, saves, publishes, fetches the result from
  the public API and revalidates it with its `ETag` for a `304`.
  - It runs inside CI's Quickstart job, because that is the only place the editor container, the
    engine, PostgreSQL and the audio volume are all up together. Standing that stack up a second
    time would cost minutes for nothing.
  - It asserts the session properties **from the outside**: the refresh cookie is `httpOnly` and
    `SameSite=Lax`, and neither `localStorage`, `sessionStorage` nor `document.cookie` holds a
    token. Those are claims the unit tests make about their own code; this checks what a browser
    actually ended up with.
  - It also covers the one thing a unit test cannot reach: that a draft is a `404` to a client while
    its editor can see it listed.
  - The first JavaScript end-to-end test in this codebase's lineage. The predecessor had no test
    infrastructure in any of its frontend applications.

- **Audio mixing, in the engine and never through a shell** — `v0.3.0`,
  [#9](https://github.com/MiladNalbandi/ludus-engine/issues/9).
  `POST /api/v1/admin/audio/mix` combines clips into a new one, behind an `AudioMixer` port.
  - **The reason this is in the engine and not the editor**: mixing in the editor makes the editor
    stateful, and a stateful editor cannot run as more than one replica. The result is stored like
    any upload, so there is nothing to restore after a restart — the predecessor kept mixes on the
    editor's own filesystem and needed a restore-from-backend hack to survive one.
  - **An argv list, never a command line.** The predecessor built an FFmpeg command as a string and
    handed it to `child_process.exec` — through a shell, with interpolated filenames — which gave
    any authenticated editor user command execution on the container. The fix is not better
    escaping; it is that there is nothing to escape. `ProcessBuilder` with a `List` reaches
    `execve` directly, and a test runs a real subprocess whose own filename is
    ``re; touch pwned.txt; corder $(whoami) `id` & | x .sh`` — a successful mix *is* the proof no
    shell saw it, because a shell would have tried to run `re;`.
  - **No client string ever becomes an argument.** Inputs are written to a per-job temporary
    directory under names derived from their index, and `AudioMixer.Source` has no field a filename
    could travel in — asserted by a test over the record's components.
  - A hard timeout, an output size cap, one directory per job removed when the result stream closes,
    and the tool's own output logged rather than returned, because it names paths inside the
    container.
  - **Off by default, in a second image.** FFmpeg is a large dependency with its own vulnerability
    history, and the roadmap is explicit that a self-hoster must never have to acquire a media
    toolchain to get a working engine. The standard image refuses with a `503` naming the image and
    the variable to change; `deploy/Dockerfile.engine-ffmpeg` builds `FROM` the engine image so the
    two cannot drift.

- **The editor's timeline, preview and behaviour panels** — `v0.3.0`,
  [#9](https://github.com/MiladNalbandi/ludus-engine/issues/9). A wave's movement sequence is edited
  as a timeline, previewed on a canvas, and saved back as the same document it was opened as.
  - **A zero-duration `jump` is folded into the next block, not drawn.** It relocates the entity
    instantly, so it occupies no time: as a block it would be an unclickable sliver, and dropped it
    would silently delete an author's instruction. It becomes the following movement's starting
    position and is unfolded on the way out. A trailing one is kept as a block, because there is
    nothing after it to fold into — the lossless option, not the tidy one.
  - **Opening a wave and saving it without touching anything produces the same document.** Asserted
    directly, because the alternative is that every author who opens a wave to look at it rewrites
    it, moving the ETag and making every client re-download the catalogue for nothing.
  - **The simulator is a pure function of time**, so seeking to a moment is identical to playing to
    it. A preview that accumulated state per frame shows an author something the game never
    produces, which makes it worse than no preview because it is convincing.
  - Movements and their editing panels resolve through **registries** —
    `simulatorRegistry.register('patrol', …)`, `behaviorEditorRegistry.register('patrol', …)` — not
    a `switch`. That is what makes `v1.1.0` a decomposition rather than a rewrite, and it means a
    movement type with nothing registered is reported to the author rather than drawn as a
    stationary dot that looks like a working entity standing still. Both registries refuse a second
    registration for one type, and a test pins each against the schema's own list of eleven.
  - The preview is a schematic and says so. The roadmap rules out a general-purpose 2D simulation,
    so what this answers is "where does each entity go, and when".

- **The editor, first release** — the foundation of `v0.3.0`,
  [#9](https://github.com/MiladNalbandi/ludus-engine/issues/9). A Next.js application under
  `editor/`, served beside the engine by `docker compose up`, holding no content of its own.
  - **The browser never talks to the engine.** Every call goes through the editor's own route
    handlers, which is what lets the refresh token live in an httpOnly cookie page JavaScript cannot
    read — and lets a deployment leave the engine unpublished entirely, reachable on the compose
    network and nowhere else, with no CORS policy to get wrong.
  - **The access token is held in memory and nowhere else.** Not `localStorage`, not
    `sessionStorage`, not a readable cookie: all three are readable by any script that reaches the
    page, so one cross-site scripting hole becomes a session that outlives the tab. The visible cost
    is a spinner on first paint while the refresh cookie is exchanged.
  - `apiFetch` refreshes **once** on a `401` and retries once, never looping — and concurrent
    callers **share one refresh**. That second rule is correct on every single request and wrong the
    moment two arrive together: the engine revokes each refresh token as it issues the next, so ten
    simultaneous refreshes mean nine presented after revocation and a session that dies for no
    visible reason. Of the thirteen tests, that is the one that fails when the sharing is removed.
  - **The wave types are generated** from `contracts/schemas/wave/v1.json` with
    `json-schema-to-typescript`, committed, and checked in CI. Hand-written types beside a schema
    drift quietly: the editor keeps compiling, the engine keeps rejecting, and the author sees a
    `422` about a field their form does not show.
  - The middleware is a redirect, not a security control, and says so. It checks only whether a
    cookie is *present*. The codebase this was extracted from had one that exempted `/api/*` because
    "they have their own auth", and some of those routes had none — which is how unauthenticated
    writes shipped. There is no filesystem content store here, and will not be.
  - Quickstart asserts the refresh cookie is `HttpOnly` and `SameSite=Lax` and that the access token
    comes back in the body. A flag that silently stopped being set would leave sessions stealable
    with nothing failing anywhere.
  - Still to come in `v0.3.0`: the timeline, the canvas preview, audio mixing, and the Playwright
    smoke test, which needs real editing UI to walk through.

- **Bulk and batch operations**, completing `v0.2.0`,
  [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8).
  - `POST /api/v1/admin/waves/bulk` imports many documents and
    `POST /api/v1/admin/waves/batch-delete` removes many, **all or nothing**. A partially applied
    import leaves an author with two problems the response cannot answer: which documents landed,
    and whether retrying duplicates them.
  - Atomicity is a `UnitOfWork` outbound port rather than `@Transactional`. The application layer
    declares no framework dependencies — the enforcer fails the build on a Spring import — and the
    annotation would in any case be *silently ignored* on an application object Spring does not
    proxy, producing a batch that looks atomic and is not. Verified by breaking it: replacing the
    `TransactionTemplate` with a bare call leaves the rest of the suite green and fails three tests.
  - Every document goes through the same `AuthorWave` as a single save — same stamping, same schema
    validation, same derived order, same collision check. A bulk endpoint that validated differently
    would be the way invalid content got in.
  - Violations carry the index of the document that caused them:
    `/3/progression_config/order`, not `/progression_config/order`. Thirty documents in, "the order
    collides" names nothing an author can open.
  - An id that is not there is a violation, not a silent skip. "Delete these six" is a statement
    about a known set, and a caller who sent a typo has a different catalogue than they think.
  - `POST /api/v1/public/waves/batch` fetches several published documents in one request, for a
    client's first launch. **The documents are embedded as stored bytes**, assembled by hand:
    handing Jackson a map of strings would escape each one into a string literal, and mapping them
    to objects would re-serialise them — either way a client revalidating with the `ETag` from
    `/raw` would be told its cache is stale forever. Not cacheable itself, which is the right trade
    for the one fetch a fresh install makes.
  - Unknown and unpublished ids are absent from a batch response rather than reported. A batch that
    distinguished "not published" from "never existed" would hand back exactly what publication
    withholds.
  - `JsonArrays` finds element boundaries without interpreting them, with 22 table rows: a comma
    inside a string, a brace inside a string, an escaped quote, an escaped backslash before a
    quote, nested arrays, a trailing comma, an unterminated string. The failure mode is silent — a
    truncated document reaches the validator, which rejects it with a schema error naming a field,
    and the author goes looking at a document that is perfectly fine.

- **Application configuration**, part of `v0.2.0`,
  [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8). The settings a game reads at launch,
  edited at `/api/v1/admin/app-config` and served from `/api/v1/public/app-config`.
  - **Free-form, deliberately.** Waves have a schema because the engine interprets them — it derives
    an order, a name and a publication state from the document. Nothing here is interpreted by the
    engine at all, so a schema would mean a release of Ludus every time a game wanted a new
    difficulty knob.
  - Stored verbatim with a generated `jsonb` column, exactly like a wave, and for the sharper
    version of the same reason: this document is fetched by every client on every launch, so a hash
    that moves when nothing changed costs more here than anywhere else.
  - One row per project, with `project_id` as the primary key. Configuration is singular; a table
    that allowed two would need a rule somewhere choosing between them.
  - **Replace, never patch.** A merge endpoint has to decide what a null means, whether an absent
    key removes or preserves, and how deep to go — three questions the engine cannot answer, since
    it does not know what any of the keys mean.
  - An unconfigured project returns `{}` rather than a `404`, because that is exactly what "no
    overrides" means. This differs from the active level, where absence is a real state a game must
    cope with.

- **Wave levels**, part of `v0.2.0`, [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8).
  Waves are sequenced into levels under `/api/v1/admin/wave-levels`, and a game client fetches the
  one being played from `/api/v1/public/wave-levels/active`.
  - **Three rules are enforced by the schema rather than by code**, and all three were application
    logic that went wrong at least once in the codebase this was extracted from. A project has at
    most one active level. A level's waves belong to the same project as the level. Deleting a wave
    removes it from every level that used it.
  - "Active" is **a table keyed by project**, not a boolean column per level. The roadmap proposed a
    partial unique index, which is PostgreSQL-only and would have had to live in
    `db/vendor/postgresql` — fine for the generated `jsonb` column, which nothing reads, and not
    fine for the one invariant the feature exists to guarantee. The slice tests run against H2, so a
    constraint that is absent there is a constraint those tests cannot prove. A primary key on
    `project_id` says the same thing in SQL every database has.
  - Membership rows are written by the adapter rather than by Hibernate. Managed as an ordered
    collection, reordering a level issued in-place updates that collided with the
    `(level, wave)` key halfway through — swapping two waves threw a constraint violation. The
    alternatives were to weaken the schema or to choose the statements; the second keeps both
    constraints.
  - **A client gets the published members; an editor is told which ones those are.** A level is
    assembled while its waves are still being written, so unpublished members are absent from the
    public route — and every authoring response marks each member's publication state, because an
    editor who cannot see which entries players are not receiving finds out from a player.
  - No active level is a `404`, not an empty level. A client must be able to tell "nothing chosen"
    from "chosen and empty".
  - The active level's `ETag` covers the level and its members, so renaming it, resequencing it or
    editing any wave inside it all move it.

- **Audio**, part of `v0.2.0`, [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8). Clips
  are uploaded by an editor under `/api/v1/admin/audio` and streamed to anyone from
  `/api/v1/public/audio/{id}`.
  - **Nothing holds a clip in memory, at either end**, and that is the whole design. The outbound
    port takes and returns `InputStream`; the controller returns a `StreamingResponseBody`; the
    upload reads `getInputStream()` and never `getBytes()`. The codebase this was extracted from
    read whole files into byte arrays and fell over on a 256 MB heap.
  - `AudioStreamingIT` runs in a JVM capped at 256 MB and pushes a clip **larger than that entire
    heap** through storage and back out over HTTP. The size is chosen so buffering cannot succeed
    by luck: two earlier drafts — one 12 MB clip, then sixteen at once — both passed against a
    deliberately buffering controller before being replaced. A guard that only fails when threads
    interleave the right way is not a guard.
  - Bytes are files under `LUDUS_AUDIO_DIRECTORY`, addressed by clip id and nothing else, so no
    client-supplied filename ever reaches a path. Writes go to a `.partial` and are moved into
    place atomically, and the directory is checked for writability at startup rather than on the
    first upload.
  - Metadata is in the database and the bytes are not. A 40 MB track in a row has to be read into
    memory to be served, and it makes every backup carry the music.
  - Content types are an allow-list. Storing and serving back whatever was uploaded would
    otherwise make this a way to host a page on the engine's own origin.
  - Served `immutable` with a year's `max-age` and no `ETag`: a clip never changes under its id,
    because a new upload is a new id. That is the one thing here that differs from wave documents.

- **The OpenAPI document is committed** at `docs/api/openapi.json`, and `OpenApiSnapshotTest` fails
  the build when it changes. A document generated at runtime agrees with the implementation by
  construction, including on the day the implementation changes by accident; committing it turns
  "the API changed" into a line in a diff somebody has to approve. That matters more as `v1.0.0`
  approaches, since that release promises a frozen contract — a promise about something nobody
  tracks is not a promise. Regenerate with
  `./mvnw -pl engine/engine-bootstrap test -Dtest=OpenApiSnapshotTest -Dludus.openapi.write=true`.

- **Public content routes**, under `/api/v1/public` — the second half of `v0.2.0`,
  [#8](https://github.com/MiladNalbandi/ludus-engine/issues/8). A game client can now fetch what an
  editor published.
  - `GET /api/v1/public/status` returns the content hash for everything published, served
    `Cache-Control: no-store`. It reads ids and timestamps only and never loads a document, because
    it is called on every launch.
  - `GET /api/v1/public/waves`, `/waves/{id}` and `/waves/{id}/raw`, each carrying an `ETag` and
    answering `304` to a matching `If-None-Match`. The raw route returns the stored bytes exactly.
  - **The status hash and the list ETag are the same value**, asserted as string equality. Computed
    separately they can disagree, and a client caught between them — told "changed" by one signal,
    handed a `304` validated against the other — is very hard to debug from either side.
  - No credential required. Published content is what every copy of the game downloads; requiring
    a secret that ships inside the binary would be one in name only. API keys remain for saying
    which client is calling, for project selection under multi-tenancy, and for rate limiting.
  - A draft is a `404`, never a `403`, as is another project's wave and one that never existed.
- `EntityTags` parses `If-None-Match` the way real clients and proxies write it: weak validators,
  quoted and unquoted, comma-separated lists, and `*`. Comparison is weak, because strong
  comparison exists for byte ranges and nothing here serves ranges. Twenty-five table rows, one per
  form seen in the wild — getting this wrong does not fail anything, it silently turns caching off
  for one platform.
- `WaveRepository.findPublished` — a published-only single lookup, so "which rows may a client see"
  is answered by the query rather than by whoever remembers to filter.

### Changed

- **Every OpenAPI operation now has an explicit `operationId`.** springdoc derives them from method
  names and disambiguates collisions by discovery order, so three unrelated operations were named
  `list_1`, `list_2`, `list_3` — and adding one controller renumbered them. The snapshot diff for
  wave levels is what surfaced it: four operations the change did not touch were renamed in the
  published contract. Generated clients break on that, and a contract that reshuffles itself is not
  one `v1.0.0` can promise to freeze.

### Fixed

- **The published contract described four different endpoints with one schema.** Four records were
  named `Summary` — waves, wave levels, audio clips and API keys — and springdoc names a schema
  after the Java class's simple name and silently keeps one of any two that collide. So
  `docs/api/openapi.json` said `GET /api/v1/admin/audio` returns `order`, `schemaVersion` and
  `published`, when it returns `filename`, `contentType` and `sizeBytes`. A generated client was
  correct for waves and wrong about the other three. Nothing failed: the document was valid, the
  endpoints worked, and only the description was untrue — which is the same failure as a green check
  that means nothing, in the one file `v1.0.0` promises to freeze.
  - Every request and response record now declares `@Schema(name = ...)`, and
    `SchemaNamesAreExplicitTest` fails the build when one does not. The snapshot test would have
    shown the collision as a diff; it would not have said what the diff meant, and "the wave-levels
    response now references Summary" reads like housekeeping.
  - The two routes returning `ResponseEntity<?>` were described as returning a bare object, which is
    as useful to a generated client as no description at all. Both now declare their body type and
    their real status codes, including the `304` and the `404`.

- **An empty request body returned `401`, on every document route.** `@RequestBody` is required by
  default, so Spring refused an empty one before any controller code ran — and that refusal goes out
  through the container's error dispatch, which re-enters the security filter chain with no
  authentication in it. A perfectly well authenticated request came back unauthenticated. It is the
  same mechanism that once turned a `403` into a `401`, and just as unreadable from outside: the
  status names the wrong problem entirely. The body is now bound leniently and rejected at the edge
  as a `422`, while the published contract still says a body is required, because it is.
- The `422` handler told every caller their document "did not satisfy the wave schema". That was the
  whole truth when waves were the only content there was; levels and application configuration are
  rejected through the same handler and neither is validated against a schema.

- Three status blurbs said there was no content API after authoring had shipped, and
  `OpenApiConfiguration`'s javadoc claimed the OpenAPI document was committed under `docs/api` and
  diffed in CI — a mechanism that did not exist. Documentation asserting something untrue is the
  same failure as a green check that means nothing. The claim was removed; it is back now, above,
  because the mechanism is.

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
