"""Finding apps and putting their routes on the service.

Two kinds of app, one manifest format, and the same mount at the end.

**Built-in apps** are the directories under `wavemaker/apps/` that ship a `manifest.toml`, and
are imported as `wavemaker.apps.<name>`. The import is dynamic, with `importlib`, and that is
the point rather than a way around the architecture wall: the wall forbids the core from
*knowing* about an app, and a loader that imports a name it was handed knows nothing.

**Installed plugins** are the directories under the plugins directory, each carrying its code
in `backend/`, and are imported from there by `code.load_backend`. They are held to their
manifest: every path the router serves must lie under `/api/v1/<name>` or a route the manifest
declares, and none may be a path another app already answers. Built-in apps ship with the
platform and are reviewed with it, so their routes are not held to a `[permissions]` table — an
installed copy of the same app is. (Migrations are judged the same way for both; see
`migrations.py`.)

The check is made once, here, against the routes the router has when it is mounted. Code that
adds a route later — to its own router, or to the application through `request.app` — is out of
reach of a check like this one; see `outbound.py` for why in-process checks stop there.

Built-ins are mounted first, then installed plugins, each in name order. Starlette answers a
request with the first route that matches, so mounting built-ins first means no plugin, however
it is named, can be put in front of one.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from importlib import import_module
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter, FastAPI
from fastapi.routing import RouteContext, iter_route_contexts
from starlette.routing import BaseRoute

from wavemaker.platform.kernel.errors import PermissionRefused, PlatformError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.kernel.permissions import refused_routes, route_prefixes
from wavemaker.platform.kernel.registry import AppRegistry
from wavemaker.platform.plugins.code import load_backend
from wavemaker.platform.plugins.loader import load_manifests

BUILTIN_APPS = Path(__file__).resolve().parents[1].parent / "apps"
MODULE_ROOT = "wavemaker.apps"

PARAMETER = re.compile(r"\{[^}]*\}")


class AppWiringError(PlatformError):
    """An app loaded, and then could not be put on the service."""


def builtin_manifests() -> list[AppManifest]:
    """The apps that ship with the platform. None of them is special to the core."""
    return load_manifests(BUILTIN_APPS)


def mount(
    app: FastAPI,
    registry: AppRegistry,
    builtins: Collection[str],
    installed: Mapping[str, Path] | None = None,
) -> None:
    """Put every app's routes on the service: built-ins first, then installed plugins.

    `installed` maps an installed plugin's name to its directory. An app in neither is a
    manifest with no code, and is refused rather than skipped: "it had no code, so it got no
    routes" is how a plugin silently stops working.
    """
    installed = installed or {}
    for manifest in registry.apps:
        if manifest.name in builtins:
            app.include_router(_router_of(manifest, _import_builtin(manifest)))

    for manifest in registry.apps:
        if manifest.name in builtins:
            continue
        directory = installed.get(manifest.name)
        if directory is None:
            raise AppWiringError(
                f"App '{manifest.name}' ({manifest.source or 'unknown'}) is registered but is "
                "neither built in nor installed, so there is no code to mount."
            )
        router = installed_router(manifest, directory)
        refuse_collisions(manifest, router.routes, app.routes)
        app.include_router(router)


def installed_router(manifest: AppManifest, directory: Path) -> APIRouter:
    """An installed plugin's router, loaded and checked against what its manifest grants."""
    router = _router_of(manifest, load_backend(manifest, directory))
    refuse_routes_outside(manifest, router.routes)
    return router


def effective_routes(routes: Sequence[BaseRoute]) -> list[RouteContext]:
    """Every route as the router will match it, with included routers' prefixes applied.

    FastAPI keeps an included router as one entry that resolves its routes when asked, so a
    router's `routes` is not the list of paths it answers. This is.
    """
    return list(iter_route_contexts(routes))


def refuse_routes_outside(manifest: AppManifest, routes: Sequence[BaseRoute]) -> None:
    paths = [_path_of(manifest, route) for route in effective_routes(routes)]
    outside = refused_routes(manifest.name, manifest.permissions, paths)
    if outside:
        allowed = ", ".join(route_prefixes(manifest.name, manifest.permissions))
        raise PermissionRefused(
            f"Plugin '{manifest.name}' ({manifest.source or 'unknown'}) serves "
            f"{', '.join(outside)}, outside what its manifest grants ({allowed})."
        )


def refuse_collisions(
    manifest: AppManifest, routes: Sequence[BaseRoute], existing: Sequence[BaseRoute]
) -> None:
    """A plugin may add paths; it may not answer one somebody else already answers."""
    taken = {key for route in effective_routes(existing) for key in _keys(route)}
    taken_paths = {path for _, path in taken}
    clashes = sorted(
        f"{method} {path}"
        for route in effective_routes(routes)
        for method, path in _keys(route)
        if (method, path) in taken
        or ("*", path) in taken
        or (method == "*" and path in taken_paths)
    )
    if clashes:
        raise PermissionRefused(
            f"Plugin '{manifest.name}' ({manifest.source or 'unknown'}) would answer "
            f"{', '.join(clashes)}, which another app already answers."
        )


def _import_builtin(manifest: AppManifest) -> ModuleType:
    module_name = f"{MODULE_ROOT}.{manifest.name}"
    try:
        return import_module(module_name)
    except ImportError as missing:
        raise AppWiringError(
            f"App '{manifest.name}' ({manifest.source or 'unknown'}) declares a manifest but "
            f"{module_name} could not be imported: {missing}"
        ) from missing


def _router_of(manifest: AppManifest, module: ModuleType) -> APIRouter:
    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise AppWiringError(
            f"App '{manifest.name}' ({module.__name__}) must expose `router`, an APIRouter. "
            "An app with no routes is not yet an app."
        )
    return router


def _path_of(manifest: AppManifest, route: RouteContext) -> str:
    path = route.path
    if not isinstance(path, str):
        raise PermissionRefused(
            f"Plugin '{manifest.name}' declares a route with no path ({route.route!r}), which "
            "cannot be held to a prefix."
        )
    return path


def _keys(route: RouteContext) -> list[tuple[str, str]]:
    """(method, path) pairs, with parameter names erased: `/a/{id}` and `/a/{key}` are one
    path to the router. A route with no methods — a websocket, a mount — takes them all."""
    path = route.path
    if not isinstance(path, str):
        return []
    shape = PARAMETER.sub("{}", path)
    methods = route.methods or {"*"}
    return [(method, shape) for method in sorted(methods)]
