# Ludus Unity SDK

Not built yet. It lands with engine `v1.5.0`.

The plan is a UPM package installed by git URL, in **its own repository** so that Unity can
resolve it and version it independently of the engine. It will:

- authenticate with a project API key,
- fetch published content, honouring the ETag and content-hash protocol the engine already
  speaks, so an offline cache is correct rather than approximate,
- build a map or level from a content document,
- run entity behaviour through a handler registry you can extend with your own behaviours,
- and expose the live-ops APIs (XP, items, currency, inventory, notifications).

A behaviour key the SDK does not recognise skips that entity, logs, and keeps playing. The
game should degrade, not stop.

## Licensing

**Apache-2.0** — see `LICENSE` in this directory, which is deliberately different from the
AGPL that covers the engine. A copyleft client library linked into a game would place
obligations on that game, which would make the SDK unusable for its actual purpose. Client
code is permissively licensed so that shipping it inside your game is unencumbered.
