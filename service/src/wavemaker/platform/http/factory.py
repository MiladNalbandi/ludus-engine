"""Building the service: read the plugins, settle which may run, then expose HTTP.

The reading and the refusing happen while the application object is being built, not in a
startup event. A manifest that is wrong therefore stops `create_app` rather than leaving a
half-built service answering some routes and failing others.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from wavemaker.platform.config import Settings
from wavemaker.platform.kernel.registry import AppRegistry
from wavemaker.platform.kernel.version import PLATFORM_VERSION
from wavemaker.platform.plugins.loader import load_manifests


def build_registry(settings: Settings) -> AppRegistry:
    registry = AppRegistry(platform_version=PLATFORM_VERSION)
    for manifest in load_manifests(settings.plugins_directory):
        registry.register(manifest)
    return registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    registry = build_registry(settings)

    app = FastAPI(title="WaveMaker", version=PLATFORM_VERSION)
    app.state.registry = registry

    @app.get("/health")
    def health() -> dict[str, Any]:
        """What is actually running: the platform version, and every app that loaded.

        The app list is the only evidence from outside that the loader ran at all, which is
        why it is here rather than behind a credential.
        """
        return {
            "status": "ok",
            "version": PLATFORM_VERSION,
            "apps": [
                {"name": app_manifest.name, "version": app_manifest.version}
                for app_manifest in registry.apps
            ],
        }

    return app
