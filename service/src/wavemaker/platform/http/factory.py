"""Building the service: read the plugins, settle which may run, then expose HTTP.

The reading and the refusing happen while the application object is being built, not in a
startup event. A manifest that is wrong therefore stops `create_app` rather than leaving a
half-built service answering some routes and failing others.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from wavemaker.platform.config import Settings
from wavemaker.platform.identity.accounts import ensure_account
from wavemaker.platform.identity.http import router as identity_router
from wavemaker.platform.identity.player_http import router as player_router
from wavemaker.platform.identity.tokens import MINIMUM_SECRET_BYTES, Role
from wavemaker.platform.kernel.errors import ConfigurationError
from wavemaker.platform.kernel.registry import AppRegistry
from wavemaker.platform.kernel.version import PLATFORM_VERSION
from wavemaker.platform.persistence.engine import (
    create_database_engine,
    create_session_factory,
    migrate,
)
from wavemaker.platform.plugins.loader import load_manifests
from wavemaker.platform.plugins.mounting import builtin_manifests, mount
from wavemaker.platform.tenancy import ensure_project


def build_registry(settings: Settings) -> AppRegistry:
    """Built-in apps first, then installed plugins, through one registry.

    Both come from the same loader reading the same manifest format, so an app that moves out
    of this repository and returns through `plugin install` is the same thing to the core. It
    also means an installed plugin cannot take a built-in app's name: the second one to
    register is refused, whichever it is.
    """
    registry = AppRegistry(platform_version=PLATFORM_VERSION)
    for manifest in [*builtin_manifests(), *load_manifests(settings.plugins_directory)]:
        registry.register(manifest)
    return registry


def builtin_names() -> set[str]:
    """The apps whose code ships with this process, and so are the only ones with routes."""
    return {manifest.name for manifest in builtin_manifests()}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    registry = build_registry(settings)

    app = FastAPI(title="WaveMaker", version=PLATFORM_VERSION)
    app.state.registry = registry
    app.state.session_factory = None
    app.state.project_id = None

    app.state.settings = settings

    if settings.database_url:
        if not settings.jwt_secret:
            # Loudly, at startup. A generated or defaulted key would let the service boot and
            # issue tokens that anybody holding this source can forge, and nothing about a
            # running service would look wrong.
            raise ConfigurationError(
                "WAVEMAKER_JWT_SECRET must be set when a database is configured: it is the key "
                "every access and refresh token is signed with."
            )
        if len(settings.jwt_secret.encode()) < MINIMUM_SECRET_BYTES:
            raise ConfigurationError(
                f"WAVEMAKER_JWT_SECRET must be at least {MINIMUM_SECRET_BYTES} bytes. A shorter "
                "key is the one secret that lets anybody mint an administrator."
            )
        # Migrate before serving. A process that answers requests against a schema it has not
        # been migrated to is the failure where every read works and one write fails hours
        # later, on a different machine, in front of players.
        migrate(settings.database_url)
        engine = create_database_engine(settings.database_url)
        app.state.session_factory = create_session_factory(engine)
        with app.state.session_factory() as session:
            app.state.project_id = ensure_project(
                session, settings.project_slug, settings.project_name
            )
            if settings.admin_email and settings.admin_password:
                ensure_account(
                    session,
                    app.state.project_id,
                    settings.admin_email,
                    settings.admin_password,
                    Role.ADMIN,
                )

    app.include_router(identity_router)
    app.include_router(player_router)
    mount(app, registry, builtin_names())

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
