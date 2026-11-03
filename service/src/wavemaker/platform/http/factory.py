"""Building the service: read the plugins, settle which may run, then expose HTTP.

The reading and the refusing happen while the application object is being built, not in a
startup event. A manifest that is wrong therefore stops `create_app` rather than leaving a
half-built service answering some routes and failing others.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wavemaker.platform.config import Settings
from wavemaker.platform.identity.accounts import ensure_account
from wavemaker.platform.identity.http import router as identity_router
from wavemaker.platform.identity.player_http import router as player_router
from wavemaker.platform.identity.tokens import MINIMUM_SECRET_BYTES, Role
from wavemaker.platform.kernel.errors import ConfigurationError
from wavemaker.platform.kernel.registry import AppRegistry
from wavemaker.platform.kernel.storable import UnstorableText
from wavemaker.platform.kernel.version import PLATFORM_VERSION
from wavemaker.platform.persistence.engine import (
    create_database_engine,
    create_session_factory,
    migrate,
)
from wavemaker.platform.plugins.loader import directory_of, load_manifests
from wavemaker.platform.plugins.migrations import migrate_app, migrations_of
from wavemaker.platform.plugins.mounting import builtin_manifests, mount
from wavemaker.platform.plugins.ui import ServedUi, served_ui, ui_router
from wavemaker.platform.storage.blobs import ensure_writable
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
    """The apps whose code ships with this process, imported from `wavemaker.apps`."""
    return {manifest.name for manifest in builtin_manifests()}


def installed_directories(settings: Settings) -> dict[str, Path]:
    """Each installed plugin's directory, from which its code and its migrations are read."""
    return {
        manifest.name: directory_of(manifest)
        for manifest in load_manifests(settings.plugins_directory)
    }


def served_screens(registry: AppRegistry, installed: dict[str, Path]) -> dict[str, ServedUi]:
    """The installed plugins whose editor screen this service serves. Never a built-in: those
    are compiled into the editor."""
    screens: dict[str, ServedUi] = {}
    for manifest in registry.apps:
        directory = installed.get(manifest.name)
        if directory is not None and (screen := served_ui(manifest, directory)) is not None:
            screens[manifest.name] = screen
    return screens


def migrate_apps(database_url: str, registry: AppRegistry) -> None:
    """Every app that carries its own history, built-in or installed, in name order."""
    for manifest in registry.apps:
        migrations = migrations_of(directory_of(manifest))
        if migrations is not None:
            migrate_app(database_url, manifest, migrations)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    registry = build_registry(settings)

    app = FastAPI(title="WaveMaker", version=PLATFORM_VERSION)
    app.state.registry = registry
    app.state.session_factory = None
    app.state.project_id = None

    app.state.settings = settings

    # Routes before the database. Loading an installed plugin's code is where it is held to
    # its routes and its module name, and a plugin refused there must not have changed the
    # database first.
    app.include_router(identity_router)
    app.include_router(player_router)
    installed = installed_directories(settings)
    mount(app, registry, builtin_names(), installed)

    # A plugin's editor screen, from its ui/ folder: served read-only, and only for a plugin that
    # was mounted above, so one refused for its code has no screen either.
    screens = served_screens(registry, installed)
    app.include_router(ui_router(screens))

    # Checked here, before anything is served: a directory that cannot be written is a
    # deployment mistake, and the moment to say so is while somebody is watching the deploy —
    # not hours later, when an author uploads something and gets a 500.
    app.state.blob_directory = (
        ensure_writable(settings.blob_directory) if settings.blob_directory else None
    )

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
        migrate_apps(settings.database_url, registry)
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

    @app.exception_handler(UnstorableText)
    def unstorable_text(_: Request, refused: UnstorableText) -> JSONResponse:
        """Text PostgreSQL cannot hold, refused by the platform's one check wherever it was
        found — by a route, naming the field, or by the database boundary for one that forgot.
        Either way the caller sent it, and the answer is theirs."""
        return JSONResponse(status_code=422, content={"detail": str(refused)})

    @app.get("/health")
    def health() -> dict[str, Any]:
        """What is actually running: the platform version, and every app that loaded.

        The app list is the only evidence from outside that the loader ran at all, which is
        why it is here rather than behind a credential. An installed plugin with an editor
        screen carries `ui`: where its bundle is, the module interface it was written for, and
        the hash recorded when it was installed, which the editor checks before running it.
        This is a platform operations route, outside the frozen v1 contract; its shape is
        written down in docs/platform/r8.md.
        """
        apps: list[dict[str, Any]] = []
        for app_manifest in registry.apps:
            entry: dict[str, Any] = {"name": app_manifest.name, "version": app_manifest.version}
            if app_manifest.name in screens:
                entry["ui"] = screens[app_manifest.name].report()
            apps.append(entry)
        return {"status": "ok", "version": PLATFORM_VERSION, "apps": apps}

    return app
