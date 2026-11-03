"""The scaffold itself: the package imports, and no app has smuggled itself in yet.

This is not a feature test. It exists so that keel has one real command to run — a stack
with no passing test cannot tell a broken toolchain from a failing criterion, which is
exactly how the previous Python attempt stalled.
"""

import importlib
import pkgutil
from pathlib import Path

import wavemaker
import wavemaker.apps


def test_the_package_imports() -> None:
    assert wavemaker.__doc__


def test_the_platform_core_is_importable_on_its_own() -> None:
    """The core must stand up without any app present. R0 depends on this staying true."""
    module = importlib.import_module("wavemaker.platform.kernel")
    assert module.__doc__


def test_every_app_that_ships_is_a_package_with_a_manifest() -> None:
    """An app is a directory with a manifest. The platform reads built-ins and installed
    plugins through the same loader, so a built-in missing its manifest would simply never
    load, with nothing to say so."""
    root = Path(wavemaker.apps.__path__[0])
    found = sorted(module.name for module in pkgutil.iter_modules(wavemaker.apps.__path__))
    assert found == ["content", "economy", "inventory", "media"]
    for name in found:
        assert (root / name / "manifest.toml").is_file(), f"{name} ships no manifest.toml"
