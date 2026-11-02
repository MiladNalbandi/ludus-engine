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
        if not candidate.is_dir() or not manifest_file.is_file():
            continue
        manifests.append(_read(manifest_file))
    return manifests


def _read(manifest_file: Path) -> AppManifest:
    source = str(manifest_file)
    try:
        with manifest_file.open("rb") as handle:
            document = tomllib.load(handle)
    except OSError as unreadable:
        raise ManifestError(f"{source}: could not be read ({unreadable}).") from unreadable
    except tomllib.TOMLDecodeError as malformed:
        raise ManifestError(f"{source}: is not valid TOML ({malformed}).") from malformed

    plugin = document.get("plugin")
    if not isinstance(plugin, dict):
        raise ManifestError(
            f"{source}: has no [plugin] table. A manifest must declare at least a name "
            "and a version under [plugin]."
        )

    return AppManifest.from_mapping(plugin, source=source)
