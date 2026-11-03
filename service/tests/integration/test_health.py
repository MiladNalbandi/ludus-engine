"""AC-1 and AC-6: the service boots, and /health says what is actually loaded.

R0 is done when these pass. /health is the only route in the platform that exists before any
app does, so it is also the only thing that can prove the loader ran.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.kernel.errors import DuplicateAppError, IncompatiblePlatformError


def write_plugin(root: Path, name: str, body: str) -> None:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "manifest.toml").write_text(body)


def test_ac1_the_service_boots_and_health_is_green() -> None:
    with TestClient(create_app(Settings(plugins_directory=None))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"], "health must report the platform version"


def test_ac2_with_no_plugins_configured_only_the_built_in_apps_are_loaded() -> None:
    """No plugins directory means no *installed* apps. The apps that ship are still there,
    because they are read by the same loader from the package's own apps directory."""
    with TestClient(create_app(Settings(plugins_directory=None))) as client:
        assert client.get("/health").json()["apps"] == [
            {"name": "content", "version": "1.0.0"},
            {"name": "economy", "version": "1.0.0"},
            {"name": "inventory", "version": "1.0.0"},
            {"name": "leaderboard", "version": "1.0.0"},
            {"name": "media", "version": "1.0.0"},
            {"name": "progression", "version": "1.0.0"},
        ]


def test_ac6_health_lists_every_loaded_app_with_its_version(tmp_path: Path) -> None:
    # Two installed plugins, named so they cannot collide with any built-in: an installed
    # plugin may not take a built-in's name, and the built-in set grows with every release.
    write_plugin(tmp_path, "achievements", '[plugin]\nname = "achievements"\nversion = "1.0.0"\n')
    write_plugin(tmp_path, "quests", '[plugin]\nname = "quests"\nversion = "2.1.0"\n')

    with TestClient(create_app(Settings(plugins_directory=tmp_path))) as client:
        apps = client.get("/health").json()["apps"]

    assert apps == [
        {"name": "achievements", "version": "1.0.0"},
        {"name": "content", "version": "1.0.0"},
        {"name": "economy", "version": "1.0.0"},
        {"name": "inventory", "version": "1.0.0"},
        {"name": "leaderboard", "version": "1.0.0"},
        {"name": "media", "version": "1.0.0"},
        {"name": "progression", "version": "1.0.0"},
        {"name": "quests", "version": "2.1.0"},
    ], "installed plugins and built-in apps are one list, in name order"


def test_ac4_two_apps_with_the_same_name_stop_the_service_starting(tmp_path: Path) -> None:
    """A refusal at startup, not a 500 later: the broken state never serves a request."""
    write_plugin(tmp_path, "first", '[plugin]\nname = "achievements"\nversion = "1.0.0"\n')
    write_plugin(tmp_path, "second", '[plugin]\nname = "achievements"\nversion = "9.9.9"\n')

    with pytest.raises(DuplicateAppError):
        create_app(Settings(plugins_directory=tmp_path))


def test_ac5_an_app_needing_a_newer_platform_stops_the_service_starting(tmp_path: Path) -> None:
    write_plugin(
        tmp_path,
        "future",
        '[plugin]\nname = "future"\nversion = "1.0.0"\nrequires_platform = ">=99"\n',
    )
    with pytest.raises(IncompatiblePlatformError):
        create_app(Settings(plugins_directory=tmp_path))
