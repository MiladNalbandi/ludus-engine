"""AC-5, AC-6 and AC-8 at startup: an installed plugin's code is imported, mounted, and held to
its manifest by the service itself — whether it arrived through `plugin install` or was copied
into the plugins directory by hand.

The outbound tests open a real listening socket on 127.0.0.1 and ask the plugin to reach it,
so "refused" means a connection that would otherwise have succeeded did not happen.
"""

from __future__ import annotations

import shutil
import socket
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.plugin_kit import write_app
from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.kernel.errors import PermissionRefused
from wavemaker.platform.plugins import code, outbound
from wavemaker.platform.plugins.mounting import AppWiringError

CALLER = """
import socket
import urllib.request

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/{name}")


@router.get("/socket")
def by_socket(port: int) -> dict[str, bool]:
    with socket.create_connection(("127.0.0.1", port), timeout=2):
        return {{"reached": True}}


@router.get("/library")
def by_library(port: int) -> dict[str, bool]:
    urllib.request.urlopen(f"http://127.0.0.1:{{port}}/", timeout=2).close()
    return {{"reached": True}}
"""


def install_by_hand(plugins: Path, folder: Path) -> Path:
    """What an operator copying a plugin into place does: the layout `plugin install` leaves."""
    target = plugins / folder.name
    (target / "backend").mkdir(parents=True)
    shutil.copy(folder / "manifest.toml", target / "manifest.toml")
    for source in folder.iterdir():
        if source.name == "migrations":
            shutil.copytree(source, target / "migrations")
        elif source.name != "manifest.toml":
            shutil.copy(source, target / "backend" / source.name)
    return target


@pytest.fixture
def plugins(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "plugins"
    directory.mkdir()
    yield directory
    for name in ("caller", "online", "noisy", "maps", "squatter"):
        sys.modules.pop(name, None)


@pytest.fixture
def listener() -> Iterator[tuple[int, list[bool]]]:
    """A server on 127.0.0.1 that records every connection it accepts and answers HTTP."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    accepted: list[bool] = []

    def serve() -> None:
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            accepted.append(True)
            with connection:
                connection.recv(1024)
                connection.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1], accepted
    server.close()


def test_ac5_a_plugin_copied_in_by_hand_is_imported_and_mounted(
    tmp_path: Path, plugins: Path
) -> None:
    install_by_hand(plugins, write_app(tmp_path / "src", "maps"))

    with TestClient(create_app(Settings(plugins_directory=plugins))) as client:
        assert client.get("/api/v1/maps/hello").json() == {"app": "maps"}

    module = sys.modules["maps"]
    assert Path(module.__file__ or "").is_relative_to(plugins), "imported from where it lives"


def test_ac5_an_installed_plugin_with_no_code_stops_the_service_starting(plugins: Path) -> None:
    """R1 left an installed plugin registered with no routes. Now its code is mounted, so a
    plugin without any is refused rather than quietly serving nothing."""
    (plugins / "hollow").mkdir()
    (plugins / "hollow" / "manifest.toml").write_text('[plugin]\nname = "hollow"\nversion = "1"\n')
    with pytest.raises(code.PluginCodeError) as refused:
        create_app(Settings(plugins_directory=plugins))
    assert "backend/__init__.py" in str(refused.value)


def test_ac5_an_installed_plugin_without_a_router_stops_the_service_starting(
    tmp_path: Path, plugins: Path
) -> None:
    install_by_hand(plugins, write_app(tmp_path / "src", "maps", code="answer = 42\n"))
    with pytest.raises(AppWiringError):
        create_app(Settings(plugins_directory=plugins))


@pytest.mark.parametrize("name", ["wavemaker", "json", "fastapi"])
def test_ac5_a_plugin_copied_in_by_hand_still_may_not_shadow_a_module(
    tmp_path: Path, plugins: Path, name: str
) -> None:
    """The install command refuses these too; the service must not rely on it having run."""
    real = sys.modules[name] if name in sys.modules else __import__(name)
    install_by_hand(plugins, write_app(tmp_path / "src", name))

    with pytest.raises(PermissionRefused) as refused:
        create_app(Settings(plugins_directory=plugins))

    assert "shadow" in str(refused.value)
    assert sys.modules[name] is real


def test_ac5_a_plugin_named_after_an_installed_package_is_refused(
    tmp_path: Path, plugins: Path
) -> None:
    """`mypy` is installed here and nothing in the service imports it. Still not the plugin's:
    the next thing to import it would get the plugin instead."""
    assert "mypy" not in code.RESERVED
    install_by_hand(plugins, write_app(tmp_path / "src", "mypy"))
    with pytest.raises(PermissionRefused) as refused:
        create_app(Settings(plugins_directory=plugins))
    assert "shadow" in str(refused.value)
    assert "mypy" not in sys.modules or not hasattr(sys.modules["mypy"], code.MARK)


def test_ac6_a_plugin_copied_in_by_hand_serving_another_apps_path_is_refused(
    tmp_path: Path, plugins: Path
) -> None:
    install_by_hand(plugins, write_app(tmp_path / "src", "squatter", prefix="/api/v1/admin/items"))
    with pytest.raises(PermissionRefused) as refused:
        create_app(Settings(plugins_directory=plugins))
    assert "/api/v1/admin/items/hello" in str(refused.value)


def test_ac6_routes_of_an_included_router_are_checked_too(tmp_path: Path, plugins: Path) -> None:
    """FastAPI keeps an included router as one entry. Its routes are still the plugin's."""
    install_by_hand(
        plugins,
        write_app(
            tmp_path / "src",
            "squatter",
            code="""
            from fastapi import APIRouter

            inner = APIRouter(prefix="/api/v1/public")


            @inner.get("/status")
            def status() -> dict[str, str]:
                return {"contentHash": "forged"}


            router = APIRouter()
            router.include_router(inner)
            """,
        ),
    )
    with pytest.raises(PermissionRefused) as refused:
        create_app(Settings(plugins_directory=plugins))
    assert "/api/v1/public/status" in str(refused.value)


def test_ac8_a_plugin_is_refused_the_network_by_default(
    tmp_path: Path, plugins: Path, listener: tuple[int, list[bool]]
) -> None:
    port, accepted = listener
    install_by_hand(
        plugins, write_app(tmp_path / "src", "caller", code=CALLER.format(name="caller"))
    )

    with TestClient(create_app(Settings(plugins_directory=plugins))) as client:
        with pytest.raises(outbound.OutboundRefused) as refused:
            client.get("/api/v1/caller/socket", params={"port": port})
        assert "caller" in str(refused.value)
        with pytest.raises(outbound.OutboundRefused):
            client.get("/api/v1/caller/library", params={"port": port})

    assert accepted == [], "no connection may have reached the listener"


def test_ac8_a_plugin_granted_the_network_reaches_it(
    tmp_path: Path, plugins: Path, listener: tuple[int, list[bool]]
) -> None:
    """The same code, granted `outbound_http`, connects — so the refusal above is the guard's
    doing and not a socket that would have failed anyway."""
    port, accepted = listener
    install_by_hand(
        plugins,
        write_app(
            tmp_path / "src",
            "online",
            code=CALLER.format(name="online"),
            permissions="[permissions]\noutbound_http = true",
        ),
    )
    with TestClient(create_app(Settings(plugins_directory=plugins))) as client:
        assert client.get("/api/v1/online/socket", params={"port": port}).json() == {
            "reached": True
        }
        assert client.get("/api/v1/online/library", params={"port": port}).status_code == 200
    assert len(accepted) == 2


def test_ac8_a_plugin_reaching_out_while_it_is_imported_is_refused(
    tmp_path: Path, plugins: Path, listener: tuple[int, list[bool]]
) -> None:
    port, accepted = listener
    install_by_hand(
        plugins,
        write_app(
            tmp_path / "src",
            "noisy",
            code=f"""
            import socket

            from fastapi import APIRouter

            socket.create_connection(("127.0.0.1", {port}), timeout=2).close()
            router = APIRouter(prefix="/api/v1/noisy")
            """,
        ),
    )
    with pytest.raises(outbound.OutboundRefused):
        create_app(Settings(plugins_directory=plugins))
    assert accepted == []
    assert "noisy" not in sys.modules, "a module that failed to load is not left half-imported"


def test_ac8_the_platform_itself_still_reaches_the_network(
    tmp_path: Path, plugins: Path, listener: tuple[int, list[bool]]
) -> None:
    """The guard is about whose code is asking. With a denied plugin loaded, the platform's
    own code — and this test's — connects as before."""
    port, accepted = listener
    install_by_hand(
        plugins, write_app(tmp_path / "src", "caller", code=CALLER.format(name="caller"))
    )
    create_app(Settings(plugins_directory=plugins))
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(b"GET / HTTP/1.0\r\n\r\n")
        assert connection.recv(1024).startswith(b"HTTP/1.0 200")
    assert accepted == [True]


def test_ac5_loading_a_plugin_again_replaces_the_earlier_copy(
    tmp_path: Path, plugins: Path
) -> None:
    install_by_hand(plugins, write_app(tmp_path / "v1", "maps"))
    create_app(Settings(plugins_directory=plugins))
    first = sys.modules["maps"]

    shutil.rmtree(plugins / "maps")
    install_by_hand(
        plugins,
        write_app(
            tmp_path / "v2",
            "maps",
            code="""
            from fastapi import APIRouter

            router = APIRouter(prefix="/api/v1/maps")


            @router.get("/hello")
            def hello() -> dict[str, str]:
                return {"app": "maps", "copy": "second"}
            """,
        ),
    )
    with TestClient(create_app(Settings(plugins_directory=plugins))) as client:
        assert client.get("/api/v1/maps/hello").json()["copy"] == "second"
    assert sys.modules["maps"] is not first
