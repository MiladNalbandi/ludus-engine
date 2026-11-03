## What and why

<!-- What changed, and the reasoning behind it. The diff shows what; it cannot show why. -->

Closes #

## How it was verified

<!-- Which tests, and anything you checked by hand. -->

- [ ] In `service/`: `python -m pytest -q`, `python -m ruff check .`, `python -m mypy .` and `lint-imports` pass
- [ ] In `editor/`, if it changed: `npm run typecheck`, `npm run lint`, `npm test` and `npm run verify:types` pass
- [ ] New behaviour has a test, or a bug fix has a test that fails without it

## Checklist

- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Documentation updated, if this changes behaviour or configuration
- [ ] Breaking change? If so, describe the migration below

<!-- Architecture rules are enforced by the build. If one fires and you think it is wrong,
     say so here rather than adding a suppression — the rules are a design decision and can
     be revised. -->
