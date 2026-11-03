"""`wavemaker plugin install <name>@<version>`: from a registry to a running plugin, or nothing.

The order is the security, so it is written out:

```
  1  find name@version in the index                       nothing read but the index
  2  read the archive's bytes                              bounded, held in memory
  3  checksum   == the index's            -- or refuse     nothing unpacked, nothing imported
  4  signature  verifies with a trusted key -- or refuse   nothing unpacked, nothing imported
     ── from here on, these are the bytes the publisher signed ──
  5  every entry checked; manifest read from memory        traversal, links, sizes
  6  the manifest is the name and version that was signed
  7  it fits: platform range, no clash with a built-in or an installed app, a module name
     nobody else has, the Python packages it needs are here
  8  unpacked into a hidden staging directory
  9  its code imported, and every route it serves held to its permissions
 10  its own migrations run, judged, and kept or rolled back      (when a database is set)
 11  moved into place in one rename
```

A failure at any step leaves the plugins directory as it was: the staging directory is removed
and nothing has been renamed into place. The service itself repeats steps 9 and 10 every time
it starts, so a plugin copied into the directory by hand is held to the same rules.
"""

from __future__ import annotations

import re
import secrets
import shutil
from dataclasses import replace
from pathlib import Path

from starlette.routing import BaseRoute

from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.kernel.errors import PackageError, TrustError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.kernel.registry import AppRegistry
from wavemaker.platform.kernel.version import PLATFORM_VERSION
from wavemaker.platform.persistence.engine import migrate
from wavemaker.platform.plugins import code, index, package, signing
from wavemaker.platform.plugins.loader import MANIFEST_FILE, load_manifests, read_manifest
from wavemaker.platform.plugins.migrations import migrate_app, migrations_of
from wavemaker.platform.plugins.mounting import (
    builtin_manifests,
    installed_router,
    refuse_collisions,
)

SPEC = re.compile(r"^(?P<name>[a-z][a-z0-9_-]*)@(?P<version>[0-9A-Za-z][0-9A-Za-z.+_-]*)$")


def parse_spec(spec: str) -> tuple[str, str]:
    match = SPEC.match(spec.strip())
    if match is None:
        raise PackageError(f"{spec!r} is not name@version, such as inventory@1.0.0.")
    return match["name"], match["version"]


def install(
    spec: str,
    *,
    registry: Path,
    plugins_directory: Path,
    trusted_keys: Path | None,
    database_url: str | None = None,
) -> AppManifest:
    name, version = parse_spec(spec)
    keys = signing.TrustedKeys.load(trusted_keys)

    entry = index.find(registry, name, version)
    data = _read_bounded(index.archive_of(registry, entry))

    actual = signing.checksum(data)
    if actual != entry.sha256:
        raise TrustError(
            f"{name}@{version} does not match the registry's checksum (index {entry.sha256}, "
            f"archive {actual}): it is not the package that was published."
        )
    keys.verify(entry.key, entry.signature, entry.name, entry.version, entry.sha256)

    checked = package.read(data)
    manifest = checked.manifest
    if (manifest.name, manifest.version) != (name, version):
        raise PackageError(
            f"The package signed as {name}@{version} declares itself "
            f"{manifest.name}@{manifest.version}."
        )

    final = plugins_directory / manifest.name
    _refuse_conflicts(manifest, plugins_directory)
    _refuse_reinstall(manifest, final)
    code.refuse_shadowing(manifest)
    code.refuse_missing_dependencies(manifest)

    plugins_directory.mkdir(parents=True, exist_ok=True)
    staging = plugins_directory / f".installing-{manifest.name}-{secrets.token_hex(4)}"
    try:
        package.unpack(checked, staging)
        staged = replace(manifest, source=str(staging / MANIFEST_FILE))
        router = installed_router(staged, staging)
        refuse_collisions(staged, router.routes, _platform_routes())

        migrations = migrations_of(staging)
        if database_url:
            # The platform's history first: an app's tables may reference the platform's.
            migrate(database_url)
            if migrations is not None:
                migrate_app(database_url, staged, migrations)

        _move_into_place(staging, final)
    except BaseException:
        code.unload(manifest)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return replace(manifest, source=str(final / MANIFEST_FILE))


def _read_bounded(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except FileNotFoundError as missing:
        raise PackageError(f"The registry lists {path.name}, which is not there.") from missing
    if size > package.MAX_ARCHIVE_BYTES:
        raise PackageError(f"{path.name} is {size} bytes; at most {package.MAX_ARCHIVE_BYTES}.")
    return path.read_bytes()


def _refuse_conflicts(manifest: AppManifest, plugins_directory: Path) -> None:
    """Every refusal the service would make at startup, made now: a built-in's name, an
    installed plugin's name or table prefix, a platform version that does not fit."""
    registry = AppRegistry(platform_version=PLATFORM_VERSION)
    for builtin in builtin_manifests():
        registry.register(builtin)
    installed = load_manifests(plugins_directory) if plugins_directory.is_dir() else []
    for other in installed:
        # The copy being replaced is not a clash; every other installed plugin may be.
        if other.name != manifest.name:
            registry.register(other)
    registry.register(manifest)


def _refuse_reinstall(manifest: AppManifest, final: Path) -> None:
    if (final / MANIFEST_FILE).is_file():
        installed = read_manifest(final / MANIFEST_FILE)
        if installed.version == manifest.version:
            raise PackageError(f"{manifest.name}@{manifest.version} is already installed.")


def _platform_routes() -> list[BaseRoute]:
    """The routes of the service as it ships, to check a plugin against before it is placed."""
    service = create_app(Settings(plugins_directory=None, database_url=None, blob_directory=None))
    return list(service.routes)


def _move_into_place(staging: Path, final: Path) -> None:
    if final.exists():
        retired = final.parent / f".replaced-{final.name}-{secrets.token_hex(4)}"
        final.rename(retired)
        staging.rename(final)
        shutil.rmtree(retired, ignore_errors=True)
    else:
        staging.rename(final)
