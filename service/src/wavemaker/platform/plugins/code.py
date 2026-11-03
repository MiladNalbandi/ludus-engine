"""Putting an installed plugin's code into this process.

An installed plugin is a directory, `<plugins>/<name>/backend/`, holding a Python package. It
is imported as the top-level module named by the plugin — `map-editor` as `map_editor` —
straight from that directory. Nothing is added to `sys.path`: a path entry would make every
file in the directory importable under any name, which is how a package shadows another.

**A plugin may not take a module name that is already somebody's.** Importing a plugin as
`wavemaker`, `json` or `fastapi` would replace that module for every caller in the process, so
a name is refused when it is the platform's, a standard library module, or anything this
interpreter can already import. The check runs at install, before a file is unpacked, and again
here, before a line of the plugin runs.

A plugin's own copy can be loaded again — after an upgrade, or by a second service built in
the same process — and the old one is dropped first. That is told apart from a collision by a
mark the loader leaves on every module it creates.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import ModuleType

from packaging.requirements import Requirement

from wavemaker.platform.kernel.errors import PermissionRefused, PlatformError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.plugins import outbound

BACKEND = "backend"
MARK = "__wavemaker_plugin__"

# Never a plugin's, whatever else is or is not installed.
RESERVED = frozenset({"wavemaker", "tests", "__main__"})


class PluginCodeError(PlatformError):
    """An installed plugin's code could not be loaded."""


def refuse_shadowing(manifest: AppManifest) -> None:
    """Refuse a plugin whose module name would replace one that is already somebody's."""
    name = manifest.import_name
    reason = _taken(name)
    if reason is not None:
        raise PermissionRefused(
            f"Plugin '{manifest.name}' ({manifest.source or 'unknown'}) would be imported as "
            f"'{name}', which would shadow {reason}. Rename the plugin."
        )


def refuse_missing_dependencies(manifest: AppManifest) -> None:
    """Every distribution the plugin says it imports is installed, at a version it accepts.

    The platform never installs one: installing a package runs its build, which is code from
    a third party nobody signed. It says what is missing, and an operator decides.
    """
    missing: list[str] = []
    for line in manifest.python_dependencies:
        requirement = Requirement(line)
        try:
            found = version(requirement.name)
        except PackageNotFoundError:
            missing.append(f"{line} (not installed)")
            continue
        if not requirement.specifier.contains(found, prereleases=True):
            missing.append(f"{line} (found {found})")
    if missing:
        raise PluginCodeError(
            f"Plugin '{manifest.name}' needs Python packages this service does not have: "
            f"{'; '.join(missing)}."
        )


def load_backend(manifest: AppManifest, directory: Path) -> ModuleType:
    """Import `<directory>/backend` as the plugin's module, held to its permissions."""
    backend = directory / BACKEND
    entry = backend / "__init__.py"
    if not entry.is_file():
        raise PluginCodeError(
            f"Plugin '{manifest.name}' ({directory}) has no {BACKEND}/__init__.py. An "
            "installed plugin carries its code, and one without code has nothing to mount."
        )

    name = manifest.import_name
    _forget_earlier_copy(name)
    refuse_shadowing(manifest)
    refuse_missing_dependencies(manifest)

    spec = importlib.util.spec_from_file_location(
        name, entry, submodule_search_locations=[str(backend)]
    )
    if spec is None or spec.loader is None:
        raise PluginCodeError(f"Plugin '{manifest.name}': {entry} is not importable.")

    module = importlib.util.module_from_spec(spec)
    setattr(module, MARK, str(backend.resolve()))
    # Denied before the first line runs, so code at the top of a module is held too.
    outbound.deny(manifest)
    sys.modules[name] = module
    try:
        with outbound.acting_as(manifest):
            spec.loader.exec_module(module)
    except BaseException:
        _forget(name)
        raise
    return module


def unload(manifest: AppManifest) -> None:
    """Drop this plugin's modules, if this loader made them: after a refused install, nothing
    of the refused package stays importable."""
    _forget_earlier_copy(manifest.import_name)


def _taken(name: str) -> str | None:
    if name.startswith("wavemaker"):
        return "the platform's own package"
    if name in RESERVED:
        return "a reserved name"
    if name in sys.stdlib_module_names or name in sys.builtin_module_names:
        return "a module of the Python standard library"
    if name in sys.modules:
        if getattr(sys.modules[name], MARK, None) is not None:
            return None  # an earlier copy of a plugin by this name, which loading replaces
        return "a module this process has already imported"
    try:
        found = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        found = None
    if found is not None:
        return f"a module already installed here ({found.origin or 'a namespace package'})"
    return None


def _forget_earlier_copy(name: str) -> None:
    """Drop a copy this loader made earlier. A module it did not make is left alone, and the
    shadowing check that follows refuses the name."""
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, MARK, None) is not None:
        _forget(name)


def _forget(name: str) -> None:
    for loaded in [key for key in sys.modules if key == name or key.startswith(name + ".")]:
        del sys.modules[loaded]
