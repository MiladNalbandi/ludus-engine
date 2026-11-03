"""What a plugin may do, as its manifest's `[permissions]` table says, and the rules that hold
it to that.

The rules are plain functions over names and paths, so they can be read and tested without a
database or a web framework. The adapters gather the facts — which tables a migration really
created, which paths a router really serves — and ask these functions whether they are allowed.
A plugin's claim is never the evidence: what it did is.

Every key is checked and an unknown key is refused. A typo such as `outbound_htpp = false`
quietly falling back to a default is how a permission nobody granted ends up granted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from wavemaker.platform.kernel.errors import ManifestError

# The only value `tables` can take today. It is a string rather than a boolean so a later
# release can add a grant (read access to a named table, say) without changing what this means.
OWN_TABLES = "own"

API_ROOT = ("api", "v1")

# A literal path segment, or a `{parameter}`. Nothing else may appear in a declared route.
LITERAL = re.compile(r"^[A-Za-z0-9._~-]+$")
PARAMETER = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")
EVENT = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z0-9_-]+)+$")

KNOWN_KEYS = frozenset({"tables", "routes", "outbound_http", "events", "storage"})


@dataclass(frozen=True, slots=True)
class Permissions:
    """A plugin's grants. The defaults are the narrowest a working plugin can have: its own
    tables, its own route prefix, and no network."""

    tables: str = OWN_TABLES
    routes: tuple[str, ...] = ()
    outbound_http: bool = False
    publishes: tuple[str, ...] = ()
    subscribes: tuple[str, ...] = ()
    blobs: bool = False
    quota_mb: int | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None, *, source: str = "") -> Permissions:
        where = source or "manifest"
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise ManifestError(f"{where}: [permissions] must be a table.")

        unknown = sorted(set(data) - KNOWN_KEYS)
        if unknown:
            raise ManifestError(
                f"{where}: [permissions] does not know {', '.join(unknown)}. "
                f"A permission is one of {', '.join(sorted(KNOWN_KEYS))}."
            )

        tables = data.get("tables", OWN_TABLES)
        if tables != OWN_TABLES:
            raise ManifestError(
                f"{where}: tables = {tables!r} is not a grant this platform makes. "
                f"A plugin owns the tables with its own prefix: tables = \"{OWN_TABLES}\"."
            )

        outbound = data.get("outbound_http", False)
        if not isinstance(outbound, bool):
            raise ManifestError(f"{where}: outbound_http must be true or false.")

        publishes, subscribes = _events(data.get("events"), where)
        blobs, quota = _storage(data.get("storage"), where)

        return cls(
            tables=OWN_TABLES,
            routes=tuple(_route(route, where) for route in _strings(data, "routes", where)),
            outbound_http=outbound,
            publishes=publishes,
            subscribes=subscribes,
            blobs=blobs,
            quota_mb=quota,
        )


def table_prefix(name: str) -> str:
    """`map-editor` owns `map_editor_*`: a hyphen cannot appear in an unquoted SQL name."""
    return name.replace("-", "_") + "_"


def own_route_prefix(name: str) -> str:
    return "/" + "/".join((*API_ROOT, name))


def route_prefixes(name: str, permissions: Permissions) -> tuple[str, ...]:
    """Where a plugin may answer: under its own name, and under the paths it declared."""
    return (own_route_prefix(name), *permissions.routes)


def route_is_allowed(path: str, prefixes: Iterable[str]) -> bool:
    """Whether `path` lies under one of `prefixes`, compared segment by segment.

    A `{parameter}` in a declared prefix stands for any one segment. A parameter in the *route*
    where the prefix has a literal does not match: `/api/v1/admin/{anything}` would answer every
    other app's admin paths, and is exactly what a prefix exists to stop.
    """
    route = _segments(path)
    return any(_under(route, _segments(prefix)) for prefix in prefixes)


def refused_routes(name: str, permissions: Permissions, paths: Iterable[str]) -> list[str]:
    allowed = route_prefixes(name, permissions)
    return sorted({path for path in paths if not route_is_allowed(path, allowed)})


def is_own(relation: str, prefix: str) -> bool:
    return relation.startswith(prefix) and len(relation) > len(prefix)


def prefixes_overlap(first: str, second: str) -> bool:
    """`inv_` and `inv_x_` overlap: every name the second owns, the first could claim."""
    return first.startswith(second) or second.startswith(first)


def _under(route: Sequence[str], prefix: Sequence[str]) -> bool:
    if len(prefix) > len(route):
        return False
    for wanted, actual in zip(prefix, route, strict=False):
        if PARAMETER.match(wanted):
            continue
        if wanted != actual:
            return False
    return True


def _segments(path: str) -> list[str]:
    return path.strip("/").split("/")


def _route(route: str, where: str) -> str:
    segments = route.split("/")
    usable = (
        route.startswith("/")
        and not route.endswith("/")
        and len(segments) >= 4
        and tuple(segments[1:3]) == API_ROOT
        and LITERAL.match(segments[3]) is not None
        and all(LITERAL.match(part) or PARAMETER.match(part) for part in segments[1:])
        and not any(part in (".", "..") for part in segments)
    )
    if not usable:
        raise ManifestError(
            f"{where}: route {route!r} is not a usable prefix. A route is a path under "
            "/api/v1/ whose first segment after it is fixed text, such as /api/v1/admin/items "
            "or /api/v1/admin/players/{player_id}/inventory."
        )
    return route


def _strings(data: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"{where}: {key} must be a list of strings.")
    return tuple(value)


def _events(value: Any, where: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if value is None:
        return (), ()
    if not isinstance(value, Mapping) or set(value) - {"publish", "subscribe"}:
        raise ManifestError(f"{where}: events must be a table of publish and subscribe lists.")
    publish = _strings(value, "publish", where)
    subscribe = _strings(value, "subscribe", where)
    for event in (*publish, *subscribe):
        if not EVENT.match(event):
            raise ManifestError(
                f"{where}: {event!r} is not an event name. Use app.event, such as map.saved."
            )
    return publish, subscribe


def _storage(value: Any, where: str) -> tuple[bool, int | None]:
    if value is None:
        return False, None
    if not isinstance(value, Mapping) or set(value) - {"blobs", "quota_mb"}:
        raise ManifestError(f"{where}: storage must be a table of blobs and quota_mb.")
    blobs = value.get("blobs", False)
    quota = value.get("quota_mb")
    if not isinstance(blobs, bool):
        raise ManifestError(f"{where}: storage.blobs must be true or false.")
    if quota is not None and (isinstance(quota, bool) or not isinstance(quota, int) or quota < 1):
        raise ManifestError(f"{where}: storage.quota_mb must be a whole number above zero.")
    return blobs, quota
