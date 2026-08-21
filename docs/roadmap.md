# Roadmap

The live roadmap is **[issue #18](https://github.com/MiladNalbandi/ludus-engine/issues/18)**,
with one issue per phase. This page explains the shape of it; the issues carry the detail and
the current state.

| | Release | |
|---|---|---|
| ✅ | `v0.0.1` | Foundation: build, architecture guardrails, content contract, running service |
| 🚧 | `v0.1.0` | Identity: JWT, roles, API keys, the project boundary |
| 📋 | `v0.2.0` | Content API: author, validate, publish and serve, with ETag caching |
| 📋 | `v0.3.0` | The editor: timeline, live preview, audio, level sequencer |
| 📋 | `v0.4.0` | Live-ops: players, items, XP, currency, inventory, leaderboards |
| 📋 | `v1.0.0` | Frozen HTTP contract, documentation, semantic-versioning commitment |
| 📋 | `v1.1.0` | Plugin substrate: entity, behaviour and content types become data |
| 📋 | `v1.2.0` | Schema-driven editor, pluggable preview |
| 📋 | `v1.3.0` | Maps and blocks: the tilemap content type |
| 📋 | `v1.4.0` | Notification centre: templates, player segments, scheduling |
| 📋 | `v1.5.0` | Game client SDK (separate repository, Apache-2.0) |
| 📋 | `v2.0.0` | Multi-tenancy and hosted deployment |

## Two ordering choices worth explaining

**Identity before content.** Building authentication while the protected surface is one endpoint
is much cheaper than retrofitting it across a finished API. The codebase Ludus was extracted from
shows the failure mode: an admin check copy-pasted into eight route files, none of which actually
verified that the user was an admin.

**Generalisation after the contract freeze, not before.** Phases up to `v1.0.0` build something
specific that works. The phases after take it apart into data. Generalising first would mean
designing a plugin system against imagined requirements instead of a working one — and the result
would be abstract in exactly the wrong places.

Three small decisions taken early make that late generalisation a decomposition rather than a
rewrite: a schema validator keyed by URI, two discriminator columns present from the first
migration, and a write path that carries raw JSON rather than a typed object. Everything else is
left deliberately concrete until there is a second case to generalise against.

## Deliberately not planned

- No behaviour scripting language, VM or expression evaluator. Accepting
  `"player.hp < 0.3 && wave.time > 10"` means owning a parser, a sandbox, a debugger and a
  security boundary. Conditions, if needed, are structured JSON: ugly to author, trivial to
  validate, impossible to inject.
- No plugin marketplace. Plugins are JSON files people put in a git repository.
- No general-purpose 2D physics preview. A preview that simulates any game's movement is a game
  engine; unknown content gets an honest schematic view instead.
- No message broker, second service, or orchestrator requirement. One application, one database.
