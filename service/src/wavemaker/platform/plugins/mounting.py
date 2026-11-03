"""Finding apps and putting their routes on the service.

Two things live here, and both are deliberately ignorant of any particular app.

**Built-in apps** are the directories under `wavemaker/apps/` that ship a `manifest.toml`.
They are read by exactly the same loader as an installed plugin, so an app that moves out of
this repository and comes back through `plugin install` is the same thing to the platform.

**Mounting** imports an app by the name in its manifest and asks it for a `router`. The import
is dynamic, with `importlib`, and that is the point rather than a way around the architecture
wall: the wall forbids the core from *knowing* about an app, and a loader that imports a name
it was handed knows nothing. A static `from wavemaker.apps.content import router` would be the
violation, and `lint-imports` would fail the build for it.
"""

from __future__ import annotations

from collections.abc import Collection
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, FastAPI

from wavemaker.platform.kernel.errors import PlatformError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.kernel.registry import AppRegistry
from wavemaker.platform.plugins.loader import load_manifests

BUILTIN_APPS = Path(__file__).resolve().parents[1].parent / "apps"
MODULE_ROOT = "wavemaker.apps"


class AppWiringError(PlatformError):
    """An app loaded, and then could not be put on the service."""


def builtin_manifests() -> list[AppManifest]:
    """The apps that ship with the platform. None of them is special to the core."""
    return load_manifests(BUILTIN_APPS)


def mount(app: FastAPI, registry: AppRegistry, mountable: Collection[str]) -> None:
    """Put the routes of every app in `mountable` on the service, in registry order.

    In name order, like everything else the registry hands out, so two services given the
    same apps mount the same routes in the same sequence.

    `mountable` is the set of apps whose code this process can import, which today means the
    built-in ones. An installed plugin is registered and reported by `/health`, and brings no
    routes, because nothing has put its code on the path yet — that is R5's job, and it is
    named here rather than hidden behind an import that happens to fail.
    """
    for manifest in registry.apps:
        if manifest.name in mountable:
            app.include_router(_router_of(manifest))


def _router_of(manifest: AppManifest) -> APIRouter:
    module_name = f"{MODULE_ROOT}.{manifest.name}"
    try:
        module = import_module(module_name)
    except ImportError as missing:
        raise AppWiringError(
            f"App '{manifest.name}' ({manifest.source or 'unknown'}) declares a manifest but "
            f"{module_name} could not be imported: {missing}"
        ) from missing

    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise AppWiringError(
            f"App '{manifest.name}' ({module_name}) must expose `router`, an APIRouter. "
            "An app with no routes is not yet an app."
        )
    return router
