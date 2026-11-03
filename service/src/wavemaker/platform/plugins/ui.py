"""An installed plugin's editor screen: recorded at install, reported at `/health`, served
read-only from its `ui/` folder.

```
  plugin install                       the service                         the editor
  ──────────────                       ───────────                         ──────────
  bytes verified (sha256 + signature)
  ui/<entry> hashed from those bytes
  ── installed.json ──────────────▶    /health: "ui": {entry, api,  ──▶   fetches the entry,
                                       integrity}                          hashes what arrived,
                                       GET /plugins/<name>/<version>/       runs it only if the
                                           ui/<file>  ─────────────────▶   hashes are equal
```

**The integrity comes from the signed archive, never from the disk.** The installer hashes the
entry out of the archive it has just verified, before a byte is unpacked, and writes it into the
plugin's install record. The route serves whatever is on the disk now. If the two differ — the
file was changed after install, or by anything between the service and the browser — the
editor's check fails and the screen is not run. A package cannot forge its own record: the
archive format has no top-level `installed.json`, so unpacking can never write one.

**Only what `plugin install` placed gets a screen.** A plugin copied into the directory by hand
has no install record. Its backend runs, as R5 decided, but nothing vouches for its `ui/`
bytes, so `/health` gives it no `ui` entry and the route does not serve it.

**The route serves files and nothing else.** Every segment of the requested path is checked —
no empty, `.` or `..` segment, no backslash, no NUL, no hidden name — then each component is
refused if it is a link, the result must resolve inside the plugin's `ui/` directory, and the
final open refuses a link too. Only a short list of file types is served, each with its own
content type; an HTML page is not on it. Every answer carries `nosniff` and a policy that
forbids everything, so a file opened as a document cannot run a script.

Built-in apps are compiled into the editor and get no `ui` entry, whatever their manifest says.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response

from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.plugins import package

RECEIPT_FILE = "installed.json"
RECEIPT_FORMAT = 1

ROUTE = "/plugins/{name}/{version}/ui/{path:path}"

# What the editor may load from a plugin's ui/ folder, and the type each is served as. Anything
# else is a 404: a type guessed from the bytes is how a text file becomes a script.
CONTENT_TYPES: Mapping[str, str] = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".woff2": "font/woff2",
}

# Sent with every file. The policy matters only if a file is opened as a page — an SVG, say —
# and then it forbids every script, plugin, form and frame. A module the editor imports is not
# governed by it; the editor's own policy is what governs that.
SECURITY_HEADERS: Mapping[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; sandbox; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
    # The version is in the address, and one version is never installed twice with other bytes,
    # so an address names one set of bytes for good.
    "Cache-Control": "public, max-age=31536000, immutable",
}

logger = logging.getLogger(__name__)


def integrity_of(data: bytes) -> str:
    """Subresource-integrity form: `sha384-<base64>`, what a browser would compare."""
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode("ascii")


def write_receipt(
    directory: Path, checked: package.Package, *, sha256: str, key: str
) -> dict[str, Any]:
    """Record what was installed, hashing the ui entry from the verified archive in memory."""
    manifest = checked.manifest
    ui: dict[str, Any] | None = None
    if manifest.ui is not None:
        with zipfile.ZipFile(io.BytesIO(checked.data)) as archive:
            entry_bytes = archive.read(manifest.ui.path)
        ui = {
            "entry": manifest.ui.entry,
            "api": manifest.ui.api,
            "integrity": integrity_of(entry_bytes),
        }
    receipt = {
        "format": RECEIPT_FORMAT,
        "name": manifest.name,
        "version": manifest.version,
        "sha256": sha256,
        "key": key,
        "ui": ui,
    }
    with (directory / RECEIPT_FILE).open("x", encoding="utf-8") as sink:
        sink.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


@dataclass(frozen=True, slots=True)
class ServedUi:
    """One installed plugin's screen, as the service serves and reports it."""

    name: str
    version: str
    root: Path
    entry: str
    api: int
    integrity: str

    @property
    def entry_url(self) -> str:
        return (
            f"/plugins/{quote(self.name, safe='')}/{quote(self.version, safe='')}"
            f"/ui/{quote(self.entry, safe='')}"
        )

    def report(self) -> dict[str, Any]:
        return {"entry": self.entry_url, "api": self.api, "integrity": self.integrity}


def served_ui(manifest: AppManifest, directory: Path) -> ServedUi | None:
    """The screen of an installed plugin, or None when it has none the service can vouch for."""
    if manifest.ui is None:
        return None
    receipt = _read_receipt(directory / RECEIPT_FILE)
    recorded = receipt.get("ui") if receipt else None
    if (
        receipt is None
        or receipt.get("name") != manifest.name
        or receipt.get("version") != manifest.version
        or not isinstance(recorded, dict)
        or recorded.get("entry") != manifest.ui.entry
        or recorded.get("api") != manifest.ui.api
        or not isinstance(recorded.get("integrity"), str)
    ):
        logger.warning(
            "Plugin '%s' declares a screen, but %s has no install record for it, so its ui/ is "
            "not served. Install it with `wavemaker plugin install` to give it one.",
            manifest.name,
            directory,
        )
        return None
    return ServedUi(
        name=manifest.name,
        version=manifest.version,
        root=directory / package.UI,
        entry=manifest.ui.entry,
        api=manifest.ui.api,
        integrity=recorded["integrity"],
    )


def _read_receipt(path: Path) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict) or document.get("format") != RECEIPT_FORMAT:
        return None
    return document


def resolve_inside(root: Path, requested: str) -> Path | None:
    """The file `requested` names under `root`, or None if it is not a plain file in there.

    Checked three ways, each enough on its own for the cases it covers: the text of every
    segment, every component on the disk (no links), and where the result finally resolves.
    """
    segments = requested.split("/")
    for segment in segments:
        if (
            segment in ("", ".", "..")
            or segment.startswith(".")
            or "\\" in segment
            or "\x00" in segment
            or ":" in segment
        ):
            return None

    base = root.resolve()
    current = root
    for segment in segments:
        current = current / segment
        try:
            mode = current.lstat().st_mode
        except OSError:
            return None
        if stat.S_ISLNK(mode):
            return None

    try:
        resolved = current.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(base) or not resolved.is_file():
        return None
    return resolved


def read_plain_file(path: Path) -> bytes | None:
    """The bytes of `path`, refusing a link swapped in since it was checked."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            return None
        return source.read()


def ui_router(served: Mapping[str, ServedUi]) -> APIRouter:
    """`GET /plugins/<name>/<version>/ui/<file>`: open, like `/health`, and read-only.

    Open because a screen's code is not a secret and the editor loads it before any screen has
    run. What it may do once running is the editor's policy and the install's trust decision,
    not this route's.
    """
    router = APIRouter()

    @router.get(ROUTE, include_in_schema=False)
    def plugin_ui(name: str, version: str, path: str) -> Response:
        ui = served.get(name)
        if ui is None or ui.version != version:
            raise HTTPException(status_code=404, detail="No such plugin screen.")
        target = resolve_inside(ui.root, path)
        media_type = CONTENT_TYPES.get(target.suffix.lower()) if target else None
        data = read_plain_file(target) if target and media_type else None
        if data is None or media_type is None:
            raise HTTPException(status_code=404, detail="No such file in the plugin's ui/.")
        return Response(content=data, media_type=media_type, headers=dict(SECURITY_HEADERS))

    return router
