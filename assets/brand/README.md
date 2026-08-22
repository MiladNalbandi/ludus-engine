# Ludus brand assets

## The mark

A bold **L**, with a blue parallelogram forming the leading edge of its foot. It is lifted from
the `LUDUS` wordmark in the project illustration, reduced to the part that survives being small.

It is solid geometry with one accent shape and no fine detail, which is the whole point: it holds
at 16 px, so there is one mark rather than a display version and a favicon version.

## Files

**Sources**

| File | Use |
|---|---|
| `logo-mark.svg` | The mark. Light backgrounds |
| `logo-mark-dark.svg` | The mark on dark backgrounds — L in white, slash unchanged |
| `logo-mark-mono.svg` | One colour, inherits `currentColor`. Print, embroidery, anywhere colour is unavailable |
| `logo-horizontal.svg` | Mark + `LUDUS` + `GAME BACKEND ENGINE`, light background |
| `logo-horizontal-dark.svg` | Same, dark background |

**Exports**

| File | Use |
|---|---|
| `logo-horizontal.png` | README and docs on a light ground. Transparent background |
| `logo-horizontal-dark.png` | Same, dark ground. Transparent background |
| `logo-horizontal-on-dark.png` | Social cards and slides. Navy background baked in |
| `logo-mark-512.png` | The mark at display size |
| `logo-mark-dark-512.png` | The mark at display size, dark ground |
| `avatar-460.png` | GitHub / LinkedIn avatar. White background |
| `favicon-16.png`, `favicon-32.png`, `favicon-64.png` | Browser tab |
| `contact-sheet.png` | Everything at once, including the small-size check |

## Palette

| | | |
|---|---|---|
| Navy | `#111F3A` | The letterform, and the dark background itself |
| Blue | `#1CA9F0` | The slash. Accent only — it appears exactly once |

## The wordmark is typeset, not drawn

`LUDUS` in the lockups is set in a bold geometric sans (`Liberation Sans` → `Arial` →
`Helvetica`, metric-compatible so it renders consistently), **not** converted to outlines.

That is a deliberate compromise, and worth knowing before you use these in print. The wordmark in
the source illustration is a specific display face with angular cuts. Reproducing it exactly needs
either the original vector or a licensed face; hand-drawing an approximation produced letterforms
that looked like an arcade font next to a clean mark, so the mark is drawn and the wordmark is
typeset.

If you license a display face later, reset the wordmark. **The mark should not change.**

For print, or anywhere the font stack may be missing, convert the text to outlines first.

## Clear space and don'ts

Keep clear space of at least the width of the L's stem on every side.

Don't recolour the L, don't move or reangle the slash, don't rotate the mark, don't add effects,
and don't stretch the lockup. The slash reads as motion because it is the only diagonal in an
otherwise square mark.

## Not here yet

The full project illustration — the isometric engine with the level above it — is the intended
README hero and social preview. It is not in this directory yet because it exists only as a raster
image that has not been added to the repository. Drop it in as `hero.png` and it can be wired into
the README header above the lockup, and composed into a 1280×640 social card.

## Licence

These assets are part of the Ludus project and released under the same terms as the repository.
