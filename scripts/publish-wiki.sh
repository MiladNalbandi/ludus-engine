#!/usr/bin/env bash
#
# Mirror docs/ into this repository's GitHub Wiki.
#
# The documentation lives in docs/ so that a behaviour change and its documentation land in the
# same commit and the same review. The wiki, if you want one, is a published copy — never edit it
# directly, because the next run of this script overwrites it.
#
#   ./scripts/publish-wiki.sh              # publish
#   ./scripts/publish-wiki.sh --dry-run    # show what would be published
#
# Requires the wiki to exist: GitHub only creates the wiki's git repository after the first page
# is saved. Enable Wikis in Settings, click "Create the first page", save anything, then run this.

set -euo pipefail

REPO_URL="${LUDUS_WIKI_REMOTE:-https://github.com/MiladNalbandi/ludus-engine.wiki.git}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Explicit source→page mapping. GitHub wiki pages are a flat namespace, so nested paths are
# flattened by hand rather than by a clever rule — when a page is renamed, this table is the
# one place that has to change, and a broken link is visible here rather than at runtime.
PAGES=(
  "docs/README.md|Home.md"
  "docs/roadmap.md|Roadmap.md"
  "docs/guides/getting-started.md|Getting-Started.md"
  "docs/concepts/content-model.md|Content-Model.md"
  "docs/concepts/caching.md|Caching-and-Change-Detection.md"
  "docs/architecture/overview.md|Architecture-Overview.md"
  "docs/architecture/hexagonal.md|Hexagonal-Rules.md"
  "docs/operations/configuration.md|Configuration.md"
  "docs/operations/deployment.md|Deployment.md"
)

rewrite_links() {
  # Point inter-document links at the flattened wiki page names, and send links that leave docs/
  # (CONTRIBUTING, SECURITY, source files) back to the repository on GitHub.
  sed -E \
    -e 's#\]\((\.\./)*guides/getting-started\.md\)#](Getting-Started)#g' \
    -e 's#\]\((\.\./)*concepts/content-model\.md\)#](Content-Model)#g' \
    -e 's#\]\((\.\./)*concepts/caching\.md\)#](Caching-and-Change-Detection)#g' \
    -e 's#\]\((\.\./)*architecture/overview\.md\)#](Architecture-Overview)#g' \
    -e 's#\]\((\.\./)*architecture/hexagonal\.md\)#](Hexagonal-Rules)#g' \
    -e 's#\]\((\.\./)*operations/configuration\.md\)#](Configuration)#g' \
    -e 's#\]\((\.\./)*operations/deployment\.md\)#](Deployment)#g' \
    -e 's#\]\((\.\./)*roadmap\.md\)#](Roadmap)#g' \
    -e 's#\]\((\.\./)*architecture/adr/\)#](https://github.com/MiladNalbandi/ludus-engine/tree/main/docs/architecture/adr)#g' \
    -e 's#\]\(\.\./\.\./([A-Z]+)\.md\)#](https://github.com/MiladNalbandi/ludus-engine/blob/main/\1.md)#g' \
    -e 's#\]\(\.\./([A-Z]+)\.md\)#](https://github.com/MiladNalbandi/ludus-engine/blob/main/\1.md)#g'
}

sidebar() {
  cat <<'EOF'
### Ludus

**Start here**
- [[Getting Started|Getting-Started]]
- [[Deployment]]
- [[Configuration]]

**Concepts**
- [[The content model|Content-Model]]
- [[Caching|Caching-and-Change-Detection]]

**Architecture**
- [[Overview|Architecture-Overview]]
- [[Hexagonal rules|Hexagonal-Rules]]

**Project**
- [[Roadmap]]
- [Repository](https://github.com/MiladNalbandi/ludus-engine)
EOF
}

if $DRY_RUN; then
  echo "Would publish to $REPO_URL:"
  for entry in "${PAGES[@]}"; do
    src="${entry%%|*}"; dest="${entry##*|}"
    [[ -f "$ROOT/$src" ]] && echo "  $src  ->  $dest" || echo "  MISSING: $src"
  done
  echo "  (generated)  ->  _Sidebar.md"
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Cloning wiki..."
if ! git clone --quiet "$REPO_URL" "$WORK/wiki" 2>/dev/null; then
  cat >&2 <<EOF
Could not clone $REPO_URL

GitHub creates the wiki's git repository only after its first page is saved. Enable Wikis under
Settings, create any first page in the browser, then run this again.
EOF
  exit 1
fi

for entry in "${PAGES[@]}"; do
  src="${entry%%|*}"; dest="${entry##*|}"
  if [[ ! -f "$ROOT/$src" ]]; then
    echo "warning: $src does not exist, skipping" >&2
    continue
  fi
  rewrite_links < "$ROOT/$src" > "$WORK/wiki/$dest"
  echo "  $src -> $dest"
done
sidebar > "$WORK/wiki/_Sidebar.md"

cd "$WORK/wiki"
if git diff --quiet && git diff --cached --quiet && [[ -z "$(git status --porcelain)" ]]; then
  echo "Wiki already up to date."
  exit 0
fi

git add -A
git commit --quiet -m "docs: sync wiki from docs/ at $(git -C "$ROOT" rev-parse --short HEAD)"
git push --quiet origin HEAD
echo "Wiki updated."
