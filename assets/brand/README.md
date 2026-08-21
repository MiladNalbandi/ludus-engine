# Ludus brand assets

## The idea

Nine cells on a 3×3 grid. Five filled tiles form an **L**; the empty cells are outlined; one
amber circle sits on the grid.

It reads two ways on purpose. As a letter, it is the L of Ludus. As a picture, it is what the
engine actually does — a level built out of placed blocks, with an entity dropped onto it. The
outlined cells are the empty ones you have not filled in yet.

## Files

**Sources** — edit these, then re-export the PNGs.

| File | Use |
|---|---|
| `logo-mark.svg` | Primary mark. Light backgrounds, 48 px and above |
| `logo-mark-dark.svg` | Same mark for dark backgrounds — empty cells drawn in light ink |
| `logo-mark-simple.svg` | Solid L. **Use below 48 px**, and for favicons |
| `logo-mark-mono.svg` | One colour, inherits `currentColor`. Print, embroidery, anywhere colour is unavailable |
| `logo-horizontal.svg` | Mark + wordmark, light background |
| `logo-horizontal-dark.svg` | Mark + wordmark, dark background |

**Exports**

| File | Use |
|---|---|
| `logo-horizontal.png` | README and docs on a light ground. Transparent background |
| `logo-horizontal-dark.png` | Same, dark ground. Transparent background |
| `logo-horizontal-on-dark.png` | Social cards and slides, where transparency is not wanted. Ink background baked in |
| `logo-mark-512.png` | The mark at display size, light ground |
| `logo-mark-dark-512.png` | The mark at display size, dark ground |
| `logo-mark-simple-512.png` | The simplified mark at display size |
| `avatar-460.png` | GitHub organisation / LinkedIn avatar. White background |
| `favicon-16.png`, `favicon-32.png`, `favicon-64.png` | Browser tab |
| `contact-sheet.png` | Everything at once, including the small-size comparison |

Re-export with any SVG renderer. The exports in this directory were produced at
1200×368 (lockups), 512×512 and 460×460 (marks), and 16/32/64 (favicons).

## Why there are two marks

The detailed mark has 2-unit gaps and 2-unit outlines on a 64-unit grid. At 16 px those are half
a pixel, so they blur into a smudge. `contact-sheet.png` shows both marks rasterised at real
pixel sizes side by side — the difference is obvious and it is why the simplified mark exists.

Rule of thumb: **48 px and above, use the detailed mark. Below that, use the simplified one.**

## Palette

| | | |
|---|---|---|
| Indigo | `#5B4FE9` | Tiles, primary brand colour |
| Amber | `#FF8A3D` | The entity. Accent only — never for large areas |
| Ink | `#14142B` | Wordmark on light, and the dark background itself |

The amber is the only accent, and it appears exactly once in the mark. That is what makes it
read as a placed object rather than as decoration; using it more widely dissolves the idea.

## The wordmark

Set in a bold geometric sans with `+3` letter-spacing. The SVGs reference
`Liberation Sans / Arial / Helvetica`, which is metric-compatible and renders consistently
across platforms — but for print or anywhere the font may be missing, convert the text to
outlines first.

If you later license a display face, the wordmark is the thing to reset. The mark should not
change.

## Clear space and don'ts

Keep clear space of at least one grid cell (a quarter of the mark's height) on every side.

Don't recolour the tiles, don't rotate the mark, don't add effects, and don't reflow the grid.
The L only reads because the tiles sit where they do.

## Licence

These assets are part of the Ludus project and released under the same terms as the repository.
