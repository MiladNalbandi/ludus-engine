"""AC-4 and AC-5: the two ways a set of apps is refused, decided without touching a disk.

The registry is where "these apps may run together" is settled. It is deliberately a plain
object with no I/O, so the rules can be read without a filesystem in the way.
"""

import pytest

from wavemaker.platform.kernel.errors import DuplicateAppError, IncompatiblePlatformError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.kernel.registry import AppRegistry


def manifest(
    name: str, *, version: str = "1.0.0", requires: str = "*", source: str = ""
) -> AppManifest:
    return AppManifest(
        name=name,
        version=version,
        requires_platform=requires,
        source=source or f"{name}/manifest.toml",
    )


def test_ac2_a_registry_with_no_apps_is_a_valid_state() -> None:
    """No plugins configured is today's state and must stay a working service, not an error."""
    assert AppRegistry(platform_version="0.1.0").apps == ()


def test_ac3_apps_are_held_in_name_order_whatever_order_they_arrive_in() -> None:
    registry = AppRegistry(platform_version="0.1.0")
    for name in ("leaderboard", "content", "inventory"):
        registry.register(manifest(name))
    assert [app.name for app in registry.apps] == ["content", "inventory", "leaderboard"]


def test_ac4_two_apps_with_the_same_name_are_refused_and_both_files_are_named() -> None:
    """Whichever file wins silently, one author's app stops existing. Fail instead."""
    registry = AppRegistry(platform_version="0.1.0")
    registry.register(manifest("inventory", source="a/manifest.toml"))

    with pytest.raises(DuplicateAppError) as refused:
        registry.register(manifest("inventory", source="b/manifest.toml"))

    message = str(refused.value)
    assert "inventory" in message
    assert "a/manifest.toml" in message
    assert "b/manifest.toml" in message


def test_ac5_an_app_that_needs_a_newer_platform_is_refused() -> None:
    registry = AppRegistry(platform_version="0.1.0")
    with pytest.raises(IncompatiblePlatformError) as refused:
        registry.register(manifest("inventory", requires=">=1.2,<2"))

    message = str(refused.value)
    assert "inventory" in message
    assert ">=1.2,<2" in message, "the error must quote the range that was not met"
    assert "0.1.0" in message, "and the version that failed it"


def test_ac5_an_app_whose_range_the_platform_satisfies_is_accepted() -> None:
    registry = AppRegistry(platform_version="1.4.0")
    registry.register(manifest("inventory", requires=">=1.2,<2"))
    assert [app.name for app in registry.apps] == ["inventory"]


def test_ac5_a_range_that_is_not_a_range_is_refused_rather_than_ignored() -> None:
    """A typo in a version range must not quietly become "runs anywhere"."""
    registry = AppRegistry(platform_version="1.4.0")
    with pytest.raises(IncompatiblePlatformError):
        registry.register(manifest("inventory", requires="newer than 1.2 please"))
