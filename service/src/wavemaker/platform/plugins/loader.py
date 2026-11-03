"""Reading manifests off a disk. The adapter the kernel refuses to be.

TOML parsing and the filesystem live here so that `wavemaker.platform.kernel` stays a plain
Python module that can be tested with a dictionary. The split is checked, not just intended:
`lint-imports` fails the build if the kernel reaches for a framework.

One plugin is one directory holding a `manifest.toml`. A directory without one is not a
broken plugin, it is simply not a plugin, and is skipped in silence.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from wavemaker.platform.kernel.errors import ManifestError
from wavemaker.platform.kernel.manifest import AppManifest

MANIFEST_FILE = "manifest.toml"


def load_manifests(directory: Path | None) -> list[AppManifest]:
    """Every plugin under `directory`, or nothing at all when none is configured.

    `None` means no plugins directory was set, which is a deliberate "this service runs no
    plugins" and must keep the service starting. A directory that *was* set and is not there
    is a mistake worth hearing about, so it raises.
    """
    if directory is None:
        return []

    if not directory.is_dir():
        raise ManifestError(
            f"The plugins directory {directory} does not exist. "
            "Leave the setting empty to run with no plugins."
        )

    manifests: list[AppManifest] = []
    for candidate in sorted(directory.iterdir()):
        manifest_file = candidate / MANIFEST_FILE
        # A leading dot is the installer's: a package being unpacked, or the copy it is
        # replacing. Neither is a plugin yet, or any longer.
        if candidate.name.startswith("."):
            continue
        if not candidate.is_dir() or not manifest_file.is_file():
            continue
        manifests.append(read_manifest(manifest_file))
    return manifests


def read_manifest(manifest_file: Path) -> AppManifest:
    try:
        content = manifest_file.read_bytes()
    except OSError as unreadable:
        raise ManifestError(
            f"{manifest_file}: could not be read ({unreadable})."
        ) from unreadable
    return parse_manifest(content, source=str(manifest_file))


def parse_manifest(content: bytes, *, source: str) -> AppManifest:
    """A manifest from its bytes, wherever they came from: a file, or an archive not yet
    unpacked — which is how the installer reads one before anything touches the disk."""
    try:
        document = tomllib.loads(content.decode("utf-8"))
    except UnicodeDecodeError as malformed:
        raise ManifestError(f"{source}: is not UTF-8 ({malformed}).") from malformed
    except tomllib.TOMLDecodeError as malformed:
        raise ManifestError(f"{source}: is not valid TOML ({malformed}).") from malformed

    plugin = document.get("plugin")
    if not isinstance(plugin, dict):
        raise ManifestError(
            f"{source}: has no [plugin] table. A manifest must declare at least a name "
            "and a version under [plugin]."
        )

    return AppManifest.from_mapping(
        plugin, permissions=document.get("permissions"), ui=document.get("ui"), source=source
    )


def directory_of(manifest: AppManifest) -> Path:
    """The directory an app was read from: the one holding its manifest."""
    return Path(manifest.source).parent
