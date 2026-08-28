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

## The illustration

The project illustration — the engine opened up, the level assembled above it, the editor on one
side and the database on the other — is the README hero and the source the mark was lifted from.

| | | |
|---|---|---|
| `hero.png` | 1254×1254, transparent | The complete artwork, illustration and wordmark together. Article headers, social cards, slides. |
| `hero-illustration.png` | 960×567, transparent | The illustration alone, cropped above the wordmark. This is the README header. |

The README uses the cropped version and keeps the theme-aware lockup beneath it, because the
wordmark in `hero.png` is navy and would disappear against a dark background. The illustration
itself has no flat backdrop, so it sits correctly in either GitHub theme.

## Licence

These assets are part of the Ludus project and released under the same terms as the repository.
