"""The scaffold itself: the package imports, and no app has smuggled itself in yet.

This is not a feature test. It exists so that keel has one real command to run — a stack
with no passing test cannot tell a broken toolchain from a failing criterion, which is
exactly how the previous Python attempt stalled.
"""

import importlib
import pkgutil

import wavemaker
import wavemaker.apps


def test_the_package_imports() -> None:
    assert wavemaker.__doc__


def test_the_platform_core_is_importable_on_its_own() -> None:
    """The core must stand up without any app present. R0 depends on this staying true."""
    module = importlib.import_module("wavemaker.platform.kernel")
    assert module.__doc__


def test_no_apps_are_registered_yet() -> None:
    """The first app arrives with R1. Until then an empty `apps` package is the correct state."""
    found = [module.name for module in pkgutil.iter_modules(wavemaker.apps.__path__)]
    assert found == []
