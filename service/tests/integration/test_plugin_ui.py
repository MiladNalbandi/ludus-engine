"""R8, second half: an installed plugin's `ui/` reaches the editor — reported, served, and only
from inside its own folder.

The fixture plugin (`tests/fixtures/bulletin`) is built with `wavemaker plugin build`, signed,
published and installed exactly as an author's plugin would be. Nothing in the service names it.

What the editor relies on, and each test pins one part:

- `/health` gives an installed plugin with a screen a `ui` entry: where the bundle is, the module
  interface it was written for, and the hash the installer took from the signed archive;
- the route serves those bytes, read-only, with a JavaScript type, `nosniff` and a policy that
  forbids everything;
- a request cannot read a byte outside the plugin's `ui/` directory, however it is spelt;
- the hash is the install's, not the disk's: a file changed after install is served as it now
  is, and no longer matches what `/health` reports — which is what the editor refuses.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.asgi_stream import exchange
from tests.integration.plugin_kit import Publisher, manifest_text, minimal_entries, raw_archive
from wavemaker.platform.cli import main
from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.kernel.errors import PackageError
from wavemaker.platform.plugins import package
from wavemaker.platform.plugins.install import install
from wavemaker.platform.plugins.ui import RECEIPT_FILE

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bulletin"
ENTRY = "/plugins/bulletin/1.0.0/ui/module.js"


def sha384(data: bytes) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()


@pytest.fixture
def publisher(tmp_path: Path) -> Iterator[Publisher]:
    yield Publisher(tmp_path)
    sys.modules.pop("bulletin", None)


def install_fixture(publisher: Publisher) -> Path:
    """Build, sign, publish and install the fixture through the `wavemaker` command."""
    built = publisher.root / "built"
    assert main(["plugin", "build", str(FIXTURE), "--out", str(built)]) == 0
    archive = built / "bulletin-1.0.0.wmp"
    assert (
        main(
            [
                "plugin",
                "publish",
                str(archive),
                "--registry",
                str(publisher.registry),
                "--key",
                str(publisher.private_key),
            ]
        )
        == 0
    )
    install(
        "bulletin@1.0.0",
        registry=publisher.registry,
        plugins_directory=publisher.plugins,
        trusted_keys=publisher.trusted,
    )
    return publisher.plugins / "bulletin"


SECRET = b"not for the editor"


def plant_secrets(installed: Path) -> None:
    """Files of a type the route serves, where it must not reach: beside the plugin's code,
    hidden in its ui/, and beside the plugin in the plugins directory."""
    (installed / "backend" / "secret.js").write_bytes(SECRET)
    (installed / "ui" / ".secret.js").write_bytes(SECRET)
    (installed.parent / "outside.js").write_bytes(SECRET)


def client_for(plugins: Path) -> TestClient:
    return TestClient(create_app(Settings(plugins_directory=plugins)))


def test_r8_the_fixture_builds_into_a_package_carrying_its_ui(tmp_path: Path) -> None:
    archive = package.build(FIXTURE, tmp_path)
    checked = package.read(archive.read_bytes())

    assert "ui/module.js" in {entry.filename for entry in checked.entries}
    assert checked.manifest.ui is not None
    assert (checked.manifest.ui.entry, checked.manifest.ui.api) == ("module.js", 2)


def test_r8_installing_a_plugin_with_ui_puts_its_screen_in_health(publisher: Publisher) -> None:
    install_fixture(publisher)

    with client_for(publisher.plugins) as client:
        apps = {app["name"]: app for app in client.get("/health").json()["apps"]}

    assert apps["bulletin"] == {
        "name": "bulletin",
        "version": "1.0.0",
        "ui": {
            "entry": ENTRY,
            "api": 2,
            "integrity": sha384((FIXTURE / "ui" / "module.js").read_bytes()),
        },
    }
    # Built-in apps keep their compiled-in modules: no ui entry, and no change to their shape.
    assert apps["content"] == {"name": "content", "version": "1.0.0"}
    assert all("ui" not in app for name, app in apps.items() if name != "bulletin")


def test_r8_the_integrity_is_taken_from_the_signed_archive_at_install(
    publisher: Publisher,
) -> None:
    installed = install_fixture(publisher)
    receipt = json.loads((installed / RECEIPT_FILE).read_text())
    entry = next(e for e in json.loads((publisher.registry / "index.json").read_text())["plugins"])

    assert receipt["name"] == "bulletin" and receipt["version"] == "1.0.0"
    assert receipt["sha256"] == entry["sha256"], "the record names the archive that was verified"
    assert receipt["key"] == publisher.key_id
    assert receipt["ui"] == {
        "entry": "module.js",
        "api": 2,
        "integrity": sha384((FIXTURE / "ui" / "module.js").read_bytes()),
    }


def test_r8_the_bundle_is_served_read_only_with_its_type_and_a_strict_policy(
    publisher: Publisher,
) -> None:
    install_fixture(publisher)

    with client_for(publisher.plugins) as client:
        integrity = next(
            app["ui"]["integrity"]
            for app in client.get("/health").json()["apps"]
            if app["name"] == "bulletin"
        )
        response = client.get(ENTRY)
        refused = [client.request(method, ENTRY) for method in ("POST", "PUT", "DELETE")]

    assert response.status_code == 200
    assert response.content == (FIXTURE / "ui" / "module.js").read_bytes()
    assert sha384(response.content) == integrity, "what is served is what /health describes"
    assert response.headers["content-type"] == "text/javascript; charset=utf-8"
    assert response.headers["x-content-type-options"] == "nosniff"
    policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in policy and "sandbox" in policy
    assert "immutable" in response.headers["cache-control"]
    assert [r.status_code for r in refused] == [405, 405, 405]


def test_r8_the_route_answers_only_for_the_installed_version(publisher: Publisher) -> None:
    install_fixture(publisher)

    with client_for(publisher.plugins) as client:
        assert client.get("/plugins/bulletin/0.9.0/ui/module.js").status_code == 404
        assert client.get("/plugins/nobody/1.0.0/ui/module.js").status_code == 404
        # A built-in app has no screen served from here, whatever its name.
        assert client.get("/plugins/content/1.0.0/ui/module.js").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/plugins/bulletin/1.0.0/ui/../installed.json",
        "/plugins/bulletin/1.0.0/ui/../backend/secret.js",
        "/plugins/bulletin/1.0.0/ui/../../outside.js",
        "/plugins/bulletin/1.0.0/ui/./../backend/secret.js",
        "/plugins/bulletin/1.0.0/ui/../ui/../backend/secret.js",
        "/plugins/bulletin/1.0.0/ui/../../../../../../etc/passwd",
        "/plugins/bulletin/1.0.0/ui//etc/passwd",
        "/plugins/bulletin/1.0.0/ui/..\\backend\\secret.js",
        "/plugins/bulletin/1.0.0/ui/module.js\x00.png",
        "/plugins/bulletin/1.0.0/ui/C:/Windows/win.ini",
        "/plugins/bulletin/1.0.0/ui/.secret.js",
        "/plugins/bulletin/1.0.0/ui/",
    ],
)
def test_r8_a_ui_route_cannot_read_outside_the_plugins_ui_directory(
    publisher: Publisher, path: str
) -> None:
    """Sent to the ASGI application exactly as written: an HTTP client would tidy `..` away
    before the service ever saw it, and the test would prove nothing. The files aimed at are
    JavaScript or JSON, types the route does serve, so only the path checks stand in the way."""
    plant_secrets(install_fixture(publisher))
    app = create_app(Settings(plugins_directory=publisher.plugins))

    answer = exchange(app, method="GET", path=path)

    assert answer.status == 404
    assert SECRET not in answer.body_prefix
    assert b'"sha256"' not in answer.body_prefix
    assert b"root:" not in answer.body_prefix


def test_r8_encoded_dot_segments_cannot_leave_the_ui_directory(publisher: Publisher) -> None:
    plant_secrets(install_fixture(publisher))

    with client_for(publisher.plugins) as client:
        for path in (
            "/plugins/bulletin/1.0.0/ui/%2e%2e/backend/secret.js",
            "/plugins/bulletin/1.0.0/ui/%2E%2E%2Fbackend%2Fsecret.js",
            "/plugins/bulletin/1.0.0/ui/..%2f..%2foutside.js",
            "/plugins/bulletin/1.0.0/ui/%2Fetc%2Fpasswd",
        ):
            response = client.get(path)
            assert response.status_code == 404, path
            assert SECRET not in response.content


def test_r8_a_link_inside_ui_is_not_followed(publisher: Publisher) -> None:
    """Unpacking never writes a link; one put there afterwards is still not served."""
    installed = install_fixture(publisher)
    plant_secrets(installed)
    (installed / "ui" / "escape.js").symlink_to(installed / "backend" / "secret.js")
    (installed / "ui" / "door").symlink_to(installed / "backend", target_is_directory=True)

    with client_for(publisher.plugins) as client:
        for path in ("escape.js", "door/secret.js"):
            response = client.get(f"/plugins/bulletin/1.0.0/ui/{path}")
            assert response.status_code == 404, path
            assert SECRET not in response.content


def test_r8_only_the_file_types_the_editor_loads_are_served(publisher: Publisher) -> None:
    installed = install_fixture(publisher)
    (installed / "ui" / "page.html").write_text("<script>alert(1)</script>")
    (installed / "ui" / "notes.txt").write_text("hello")
    (installed / "ui" / "theme.css").write_text(".x { color: red }")

    with client_for(publisher.plugins) as client:
        assert client.get("/plugins/bulletin/1.0.0/ui/page.html").status_code == 404
        assert client.get("/plugins/bulletin/1.0.0/ui/notes.txt").status_code == 404
        css = client.get("/plugins/bulletin/1.0.0/ui/theme.css")

    assert css.status_code == 200
    assert css.headers["content-type"] == "text/css; charset=utf-8"


def test_r8_a_bundle_changed_after_install_no_longer_matches_what_health_reports(
    publisher: Publisher,
) -> None:
    """The record is the install's. The disk is served as it is, so the editor sees the change
    as a mismatch and refuses to run the bundle."""
    installed = install_fixture(publisher)
    original = sha384((installed / "ui" / "module.js").read_bytes())
    with (installed / "ui" / "module.js").open("a") as bundle:
        bundle.write("\nglobalThis.__bulletinTampered = true;\n")

    with client_for(publisher.plugins) as client:
        reported = next(
            app["ui"]["integrity"]
            for app in client.get("/health").json()["apps"]
            if app["name"] == "bulletin"
        )
        served = client.get(ENTRY).content

    assert reported == original
    assert sha384(served) != reported


def test_r8_a_plugin_copied_in_by_hand_has_no_screen(publisher: Publisher) -> None:
    """Its backend runs, as R5 decided. Nothing vouches for its ui/ bytes, so they are not
    offered to the editor."""
    hand_copied = publisher.plugins / "bulletin"
    shutil.copytree(FIXTURE, hand_copied / "backend", ignore=shutil.ignore_patterns("ui", "*.toml"))
    shutil.copy(FIXTURE / "manifest.toml", hand_copied / "manifest.toml")
    shutil.copytree(FIXTURE / "ui", hand_copied / "ui")

    with client_for(publisher.plugins) as client:
        apps = {app["name"]: app for app in client.get("/health").json()["apps"]}
        served = client.get(ENTRY)

    assert apps["bulletin"] == {"name": "bulletin", "version": "1.0.0"}
    assert served.status_code == 404


def test_r8_removing_the_plugin_removes_its_screen(publisher: Publisher) -> None:
    installed = install_fixture(publisher)
    with client_for(publisher.plugins) as client:
        assert client.get(ENTRY).status_code == 200

    shutil.rmtree(installed)
    sys.modules.pop("bulletin", None)

    with client_for(publisher.plugins) as client:
        names = [app["name"] for app in client.get("/health").json()["apps"]]
        assert "bulletin" not in names
        assert client.get(ENTRY).status_code == 404


def test_r8_a_folder_with_ui_and_no_ui_table_is_not_built(tmp_path: Path) -> None:
    folder = tmp_path / "bulletin"
    shutil.copytree(FIXTURE, folder)
    manifest = (folder / "manifest.toml").read_text()
    (folder / "manifest.toml").write_text(manifest.split("[ui]")[0])

    with pytest.raises(PackageError, match=r"no \[ui\] table"):
        package.build(folder, tmp_path / "out")


def test_r8_a_ui_table_naming_a_missing_file_is_not_built(tmp_path: Path) -> None:
    folder = tmp_path / "bulletin"
    shutil.copytree(FIXTURE, folder)
    (folder / "ui" / "module.js").rename(folder / "ui" / "other.js")

    with pytest.raises(PackageError, match=r"ui/module\.js"):
        package.build(folder, tmp_path / "out")


def test_r8_a_signed_package_whose_ui_entry_is_missing_is_refused_at_install(
    publisher: Publisher,
) -> None:
    ui_table = '[ui]\nentry = "module.js"\napi = 2\n'
    entries = [
        ("manifest.toml", (manifest_text("maps") + ui_table).encode()),
        *minimal_entries("maps")[1:],
        ("ui/other.js", b"export default () => ({})"),
    ]
    publisher.publish_bytes("maps", "1.0.0", raw_archive(entries))

    with pytest.raises(PackageError, match=r"ui/module\.js"):
        install(
            "maps@1.0.0",
            registry=publisher.registry,
            plugins_directory=publisher.plugins,
            trusted_keys=publisher.trusted,
        )
    leftovers = list(publisher.plugins.iterdir()) if publisher.plugins.exists() else []
    assert leftovers == []
    sys.modules.pop("maps", None)


def test_r8_a_package_from_before_r8_with_an_undeclared_ui_folder_still_installs(
    publisher: Publisher,
) -> None:
    """R5 carried ui/ without serving it, and packages built then must keep installing. Their
    folder is carried and never served."""
    entries = [*minimal_entries("maps"), ("ui/index.js", b"export default {}")]
    publisher.publish_bytes("maps", "1.0.0", raw_archive(entries))

    install(
        "maps@1.0.0",
        registry=publisher.registry,
        plugins_directory=publisher.plugins,
        trusted_keys=publisher.trusted,
    )

    with client_for(publisher.plugins) as client:
        apps = {app["name"]: app for app in client.get("/health").json()["apps"]}
        assert client.get("/plugins/maps/1.0.0/ui/index.js").status_code == 404
    assert apps["maps"] == {"name": "maps", "version": "1.0.0"}
    sys.modules.pop("maps", None)


def test_r8_the_ui_route_needs_no_token_like_health(publisher: Publisher) -> None:
    install_fixture(publisher)
    with client_for(publisher.plugins) as client:
        assert client.get(ENTRY, headers={"Authorization": "Bearer nonsense"}).status_code == 200
