# The editor

A visual editor for waves, levels and application configuration, served beside the engine by
`docker compose up`. It is a Next.js application under `editor/`, and it holds no content of its
own: everything it shows comes from the engine's HTTP API, and everything it saves goes back there.

```bash
cd deploy && docker compose up -d --build
open http://127.0.0.1:3000
```

Sign in with the administrator seeded from `LUDUS_ADMIN_EMAIL` and `LUDUS_ADMIN_PASSWORD`.

## The browser never talks to the engine

Every call goes through the editor's own route handlers, and that buys two specific things.

The **refresh token lives in an httpOnly cookie**, which page JavaScript cannot read, because the
only code that needs it runs on the editor's server. The **access token is held in memory** in a
store and nowhere else — not `localStorage`, not `sessionStorage`, not a readable cookie, all three
of which are readable by any script that gets onto the page. One cross-site scripting hole in a
design that stored the token would be a stolen session that outlives the tab and travels off the
machine.

The visible cost is that a hard refresh has no access token until the refresh cookie has been
exchanged for one. That is a spinner on first paint, and it is the right trade.

The second thing it buys is that **the engine does not have to be published at all**. In the compose
file the editor reaches it at `http://engine:8080` on the internal network. A deployment can expose
the editor only, and there is then no engine API on the internet to get a CORS policy wrong on.

## `apiFetch` refreshes once, and shares the refresh

A `401` triggers one refresh and one retry, never a loop: an expired refresh token would otherwise
become an endless pair of requests, and the symptom is a hung page rather than a login prompt.

Concurrent callers share a single refresh. This is the part that is easy to miss, because it is
correct on every single request and wrong as soon as two arrive together: the engine revokes each
refresh token as it issues the next, so ten simultaneous refreshes would mean nine tokens presented
after revocation and a session that dies for no visible reason. `src/lib/api.test.ts` has a test for
it, and that test is the only one of the thirteen that fails when the sharing is removed.

## The middleware is a redirect, not a control

`src/middleware.ts` checks whether a refresh cookie is *present*. Not whether it is valid, unexpired
or unrevoked — none of which can be known without asking the engine. Its only job is to send someone
with no session to the login page instead of a page that will fail to load.

**The engine is the security control.** Every route that matters is authorised there, against the
token, on every request. The codebase Ludus was extracted from had a middleware like this one that
exempted `/api/*` on the grounds that "they have their own auth", and some of those routes had none
at all — which is how unauthenticated writes shipped.

There is no filesystem content store here and never will be. Levels are rows behind the same
JWT-protected admin API as everything else.

## The wave types are generated

`editor/src/lib/wave-schema.ts` is generated from `contracts/schemas/wave/v1.json`, committed, and
checked in CI:

```bash
cd editor && npm run generate:types   # regenerate
cd editor && npm run verify:types     # what CI runs
```

Hand-written types beside a schema are a second, unenforced copy, and they drift quietly: the editor
keeps compiling, the engine keeps rejecting, and the error reaches the author as a `422` about a
field their form does not show. CI fails on any difference, so editing the generated file by hand is
not a shortcut — it is a broken build.

## Working on it

```bash
cd editor
npm install
LUDUS_ENGINE_URL=http://localhost:8080 npm run dev
npm test
npm run lint && npm run typecheck
```

`LUDUS_ENGINE_URL` has no default on purpose. An editor pointed at the wrong engine writes content
into the wrong database.

## Editing a wave

Click a wave in the catalogue. Its movement sequence appears as a timeline, one row per spawn rule,
with block widths proportional to duration — so an author sees that the orbit lasts four times as
long as the dash without reading two numbers.

**A zero-duration `jump` has no block.** It relocates the entity instantly, so it occupies no time;
drawn as a block it would be a sliver nobody can click. It is folded into the following movement as
that movement's starting position, marked with a `↷`, and unfolded again when the document is saved.
A *trailing* zero-duration jump is kept as a block, because there is nothing after it to fold into.
That asymmetry is deliberate: the alternative silently deletes an instruction the author wrote.

Opening a wave and saving it without changing anything produces the same document. There is a test
for that, because the alternative is that everyone who opens a wave to look at it rewrites it — and
the ETag is a hash of the bytes, so every client would re-download the catalogue for nothing.

## The preview is a schematic

It shows where each entity goes and when. It is **not** a reproduction of the game: the roadmap
rules out a general-purpose 2D simulation, because a preview that faithfully simulates any game's
movement is a game engine, and building one against unknown content means guessing. Anything that
depends on the real game's feel has to be checked in the real game.

It is a pure function of time, which is what makes scrubbing trustworthy: arriving at 4.2 seconds by
dragging the playhead gives exactly the picture that playing to 4.2 seconds gives. A simulator that
advanced internal state per frame would not, and an author checking their work against it would be
checking against something the game never shows.

A movement type with no registered simulator is **named** in the preview rather than drawn — a
stationary dot looks like a working entity standing still.

## Registries, not switches

Both the movement behaviours and their editing panels are looked up in a map:

```ts
simulatorRegistry.register('patrol', PatrolSimulator);
behaviorEditorRegistry.register('patrol', PatrolEditor);
```

The predecessor dispatched roughly 3,400 lines of hand-written forms through `switch (action.type)`.
A registry is the shape `v1.1.0` needs — entity, behaviour and content types becoming data — so a
plugin registers a panel and nothing else changes. Registering twice throws, because two behaviours
claiming one type means whichever loaded last silently wins.

`teleport` and `jump` fall through to a raw JSON editor on purpose: both configure spawn positions,
which needs a position picker that does not exist yet, and a half-built one that wrote the wrong
shape would be worse than a JSON field.

## Not here yet

Audio mixing, and the Playwright smoke test. The mixing decision `v0.3.0` calls for — never through
a shell — is not built, and no audio mixing happens in the editor at all today. The Playwright test
covers logging in, building, previewing, publishing and fetching from the public API; it needs a
running stack, so it lands with CI rather than as a local-only check.
