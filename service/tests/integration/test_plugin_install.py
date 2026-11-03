"""AC-2, AC-4, AC-5, AC-6 and AC-7 through the install command: from a registry to a plugin, or
to nothing at all.

Every refusal is checked for two things: that it happened, with the reason named, and that it
left nothing behind — no plugin directory, no staging directory, no module imported. A check
that refuses only after the package was unpacked or imported has already lost.
"""

from __future__ import annotations

import base64
import sys
import tomllib
from collections.abc import Iterator
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.integration.plugin_kit import (
    Entry,
    Publisher,
    minimal_entries,
    raw_archive,
    revision,
    symlink_entry,
    write_app,
)
from wavemaker.platform.cli import main
from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.kernel.errors import (
    DuplicateAppError,
    IncompatiblePlatformError,
    PackageError,
    PermissionRefused,
    TrustError,
)
from wavemaker.platform.plugins import code, index, package, signing
from wavemaker.platform.plugins.install import install

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@pytest.fixture
def publisher(tmp_path: Path) -> Iterator[Publisher]:
    yield Publisher(tmp_path)
    for name in ("maps", "achievements", "leaderboard"):
        sys.modules.pop(name, None)


def run_install(publisher: Publisher, spec: str, database_url: str | None = None) -> None:
    install(
        spec,
        registry=publisher.registry,
        plugins_directory=publisher.plugins,
        trusted_keys=publisher.trusted,
        database_url=database_url,
    )


def assert_nothing_installed(publisher: Publisher, name: str = "maps") -> None:
    leftovers = list(publisher.plugins.iterdir()) if publisher.plugins.exists() else []
    assert leftovers == [], f"a refused install left {leftovers}"
    assert name not in sys.modules, "a refused package was imported"


def test_ac2_a_signed_package_installs_and_its_routes_answer(publisher: Publisher) -> None:
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))

    run_install(publisher, "maps@1.0.0")

    assert (publisher.plugins / "maps" / "backend" / "__init__.py").is_file()
    with TestClient(create_app(Settings(plugins_directory=publisher.plugins))) as client:
        assert client.get("/api/v1/maps/hello").json() == {"app": "maps"}
        assert {"name": "maps", "version": "1.0.0"} in client.get("/health").json()["apps"]


def test_ac2_a_package_changed_after_it_was_published_is_refused_before_it_is_opened(
    publisher: Publisher,
) -> None:
    entry = publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    archive = publisher.registry / entry.file
    archive.write_bytes(archive.read_bytes() + b"\x00")

    with pytest.raises(TrustError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "checksum" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac2_a_package_and_checksum_both_replaced_fail_the_signature(publisher: Publisher) -> None:
    """Whoever can edit the registry directory can change the archive and its checksum
    together. Only the publisher's key can make the signature match."""
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    evil = raw_archive(minimal_entries("maps"))
    archive = publisher.registry / "maps-1.0.0.wmp"
    archive.write_bytes(evil)
    publisher.rewrite_index(sha256=signing.checksum(evil))

    with pytest.raises(TrustError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "signature" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac2_a_signature_made_by_another_key_is_refused(publisher: Publisher) -> None:
    """The index names the trusted key; the signature was made with somebody else's."""
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    intruder = publisher.root / "intruder.pem"
    signing.generate(intruder)
    sha = signing.checksum((publisher.registry / "maps-1.0.0.wmp").read_bytes())
    publisher.rewrite_index(
        signature=signing.sign(signing.load_private(intruder), "maps", "1.0.0", sha)
    )

    with pytest.raises(TrustError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "does not verify" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac2_a_genuine_signature_by_an_untrusted_key_is_refused(publisher: Publisher) -> None:
    """A valid signature proves who signed. It proves nothing until that someone is trusted."""
    stranger = publisher.root / "stranger.pem"
    signing.generate(stranger)
    archive = package.build(write_app(publisher.root / "src", "maps"), publisher.root / "built")
    index.publish(archive, publisher.registry, stranger)

    with pytest.raises(TrustError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "does not trust" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac2_with_no_trusted_keys_nothing_can_be_installed(publisher: Publisher) -> None:
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    with pytest.raises(TrustError) as refused:
        install(
            "maps@1.0.0",
            registry=publisher.registry,
            plugins_directory=publisher.plugins,
            trusted_keys=None,
        )
    assert "No trusted keys" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac2_a_signature_cannot_be_moved_to_another_version(publisher: Publisher) -> None:
    """The signature covers the name and the version, so a genuine 0.9 cannot be listed as
    1.0 — the relabelling an unsigned name would allow."""
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    publisher.rewrite_index(version="2.0.0")
    with pytest.raises(TrustError):
        run_install(publisher, "maps@2.0.0")
    assert_nothing_installed(publisher)


def test_ac2_a_signature_that_is_not_base64_is_a_refusal_not_a_crash(
    publisher: Publisher,
) -> None:
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    publisher.rewrite_index(signature="not base64 at all!")
    with pytest.raises(TrustError):
        run_install(publisher, "maps@1.0.0")
    publisher.rewrite_index(signature=base64.b64encode(b"short").decode())
    with pytest.raises(TrustError):
        run_install(publisher, "maps@1.0.0")


def test_ac2_an_index_cannot_point_outside_its_directory(publisher: Publisher) -> None:
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    publisher.rewrite_index(file="../built/maps-1.0.0.wmp")
    with pytest.raises(PackageError):
        run_install(publisher, "maps@1.0.0")


@pytest.mark.parametrize("spec", ["maps", "maps@", "@1.0.0", "Maps@1.0.0", "maps@1.0/../x"])
def test_ac2_an_install_spec_must_be_name_at_version(publisher: Publisher, spec: str) -> None:
    with pytest.raises(PackageError):
        run_install(publisher, spec)


def test_ac3_a_signed_archive_with_a_traversal_entry_is_still_refused(
    publisher: Publisher,
) -> None:
    """A signature says who sent a package, not that it is safe to unpack."""
    publisher.publish_bytes(
        "maps",
        "1.0.0",
        raw_archive([*minimal_entries("maps"), ("backend/../../../escaped.py", b"x = 1")]),
    )
    with pytest.raises(PackageError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "escaped.py" in str(refused.value)
    assert not list(publisher.root.rglob("escaped.py"))
    assert_nothing_installed(publisher)


def test_ac3_a_signed_archive_with_a_symbolic_link_is_still_refused(
    publisher: Publisher,
) -> None:
    publisher.publish_bytes(
        "maps",
        "1.0.0",
        raw_archive([*minimal_entries("maps"), symlink_entry("backend/etc", "/etc")]),
    )
    with pytest.raises(PackageError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "symbolic link" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac4_a_package_that_needs_another_platform_is_refused(publisher: Publisher) -> None:
    publisher.publish_folder(
        write_app(publisher.root / "src", "maps", requires_platform=">=99,<100")
    )
    with pytest.raises(IncompatiblePlatformError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert ">=99,<100" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac4_a_package_that_says_it_is_something_else_is_refused(publisher: Publisher) -> None:
    """The index and signature say maps 1.0.0; the manifest inside says otherwise."""
    entries = minimal_entries("maps")
    entries[0] = ("manifest.toml", b'[plugin]\nname = "maps"\nversion = "6.6.6"\n')
    publisher.publish_bytes("maps", "1.0.0", raw_archive(entries))
    with pytest.raises(PackageError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "6.6.6" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac4_a_package_taking_a_built_in_apps_name_is_refused(publisher: Publisher) -> None:
    publisher.publish_bytes("content", "9.0.0", raw_archive(_entries_named("content", "9.0.0")))
    with pytest.raises(DuplicateAppError):
        run_install(publisher, "content@9.0.0")
    assert_nothing_installed(publisher, "content")


def test_ac4_a_package_needing_a_python_package_that_is_missing_is_refused(
    publisher: Publisher,
) -> None:
    publisher.publish_folder(
        write_app(
            publisher.root / "src",
            "maps",
            extra_plugin='python_dependencies = ["no-such-distribution-anywhere>=1"]',
        )
    )
    with pytest.raises(code.PluginCodeError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "no-such-distribution-anywhere" in str(refused.value)
    assert_nothing_installed(publisher)


@pytest.mark.parametrize("name", ["wavemaker", "json", "fastapi", "sqlalchemy"])
def test_ac5_a_package_whose_module_would_shadow_another_is_refused_before_unpacking(
    publisher: Publisher, name: str
) -> None:
    """Imported as `wavemaker`, a plugin would replace the platform for every caller."""
    before = sys.modules.get(name)
    publisher.publish_bytes(name, "1.0.0", raw_archive(_entries_named(name, "1.0.0")))

    with pytest.raises(PermissionRefused) as refused:
        run_install(publisher, f"{name}@1.0.0")

    assert "shadow" in str(refused.value)
    assert sys.modules.get(name) is before, "the real module must be the one still loaded"
    assert not publisher.plugins.exists() or list(publisher.plugins.iterdir()) == []


def test_ac6_a_package_serving_a_route_outside_its_prefix_is_refused_at_install(
    publisher: Publisher,
) -> None:
    publisher.publish_folder(
        write_app(publisher.root / "src", "maps", prefix="/api/v1/admin/waves")
    )
    with pytest.raises(PermissionRefused) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "/api/v1/admin/waves/hello" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac6_a_declared_route_still_may_not_answer_another_apps_path(
    publisher: Publisher,
) -> None:
    """A manifest may claim `/api/v1/public/waves`; content already answers it."""
    folder = write_app(
        publisher.root / "src",
        "maps",
        permissions='[permissions]\nroutes = ["/api/v1/public/waves"]',
        code="""
        from fastapi import APIRouter

        router = APIRouter()


        @router.get("/api/v1/public/waves")
        def stolen() -> list[str]:
            return ["not the catalogue"]
        """,
    )
    publisher.publish_folder(folder)
    with pytest.raises(PermissionRefused) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "GET /api/v1/public/waves" in str(refused.value)
    assert_nothing_installed(publisher)


def test_ac7_a_plugin_asking_for_a_table_outside_its_prefix_is_refused_at_install(
    publisher: Publisher, database_url: str
) -> None:
    """The issue's second done-criterion, through the install command against PostgreSQL."""
    publisher.publish_folder(
        write_app(
            publisher.root / "src",
            "achievements",
            migrations={
                "0001_tables.py": revision(
                    """
                    create table achievements_badge (id text primary key)
                    create table player_backdoor (id text primary key)
                    """
                )
            },
        )
    )

    with pytest.raises(PermissionRefused) as refused:
        run_install(publisher, "achievements@1.0.0", database_url)

    assert "public.player_backdoor" in str(refused.value)
    assert_nothing_installed(publisher, "achievements")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("select tablename from pg_tables where schemaname = 'public'")
            ).scalars()
        )
    engine.dispose()
    assert "player_backdoor" not in tables, "the refused migration must have been rolled back"
    assert "achievements_badge" not in tables, "all of it, not just the refused statement"
    assert "achievements_alembic_version" not in tables


def test_ac7_a_plugins_own_tables_are_created_at_install(
    publisher: Publisher, database_url: str
) -> None:
    publisher.publish_folder(
        write_app(
            publisher.root / "src",
            "achievements",
            migrations={
                "0001_tables.py": revision("create table achievements_badge (id text primary key)")
            },
        )
    )
    run_install(publisher, "achievements@1.0.0", database_url)

    engine = create_engine(database_url)
    with engine.connect() as connection:
        version = connection.execute(
            text("select version_num from achievements_alembic_version")
        ).scalar_one()
        owned = set(
            connection.execute(
                text("select object from wavemaker_app_object where app = 'achievements'")
            ).scalars()
        )
    engine.dispose()
    assert version == "0001"
    assert "relation public.achievements_badge" in owned


def test_ac2_the_cli_builds_signs_publishes_and_installs(publisher: Publisher) -> None:
    folder = write_app(publisher.root / "src", "maps")
    private = publisher.root / "cli-key.pem"
    out = publisher.root / "cli-built"
    trusted = publisher.root / "cli-trusted"
    trusted.mkdir()

    assert main(["plugin", "keygen", str(private)]) == 0
    (trusted / "cli.pub").write_bytes(private.with_suffix(".pub").read_bytes())
    assert main(["plugin", "build", str(folder), "--out", str(out)]) == 0
    assert (
        main(
            [
                "plugin",
                "publish",
                str(out / "maps-1.0.0.wmp"),
                "--registry",
                str(publisher.root / "cli-registry"),
                "--key",
                str(private),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plugin",
                "install",
                "maps@1.0.0",
                "--registry",
                str(publisher.root / "cli-registry"),
                "--plugins-dir",
                str(publisher.plugins),
                "--trusted-keys",
                str(trusted),
            ]
        )
        == 0
    )
    assert (publisher.plugins / "maps" / "manifest.toml").is_file()


def test_ac2_the_cli_prints_a_refusal_and_exits_non_zero(
    publisher: Publisher, capsys: pytest.CaptureFixture[str]
) -> None:
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    status = main(
        [
            "plugin",
            "install",
            "maps@1.0.0",
            "--registry",
            str(publisher.registry),
            "--plugins-dir",
            str(publisher.plugins),
            "--trusted-keys",
            str(publisher.root / "src"),
        ]
    )
    assert status == 1
    assert capsys.readouterr().err.startswith("refused: No trusted keys")


def test_ac2_the_wavemaker_console_script_runs_the_cli() -> None:
    """Read from pyproject and resolved, so a clean checkout with no install step proves it."""
    with PYPROJECT.open("rb") as handle:
        scripts = tomllib.load(handle)["project"]["scripts"]
    assert scripts["wavemaker"] == "wavemaker.platform.cli:main"
    installed = [e for e in entry_points(group="console_scripts") if e.name == "wavemaker"]
    if installed:
        assert installed[0].load() is main


def test_ac2_installing_the_version_already_installed_is_refused(publisher: Publisher) -> None:
    publisher.publish_folder(write_app(publisher.root / "src", "maps"))
    run_install(publisher, "maps@1.0.0")
    with pytest.raises(PackageError) as refused:
        run_install(publisher, "maps@1.0.0")
    assert "already installed" in str(refused.value)


def test_ac2_a_newer_version_replaces_the_installed_one(publisher: Publisher) -> None:
    publisher.publish_folder(write_app(publisher.root / "v1", "maps"))
    publisher.publish_folder(write_app(publisher.root / "v2", "maps", version="1.1.0"))
    run_install(publisher, "maps@1.0.0")
    run_install(publisher, "maps@1.1.0")
    assert sorted(p.name for p in publisher.plugins.iterdir()) == ["maps"]
    assert 'version = "1.1.0"' in (publisher.plugins / "maps" / "manifest.toml").read_text()


def _entries_named(name: str, version: str) -> list[Entry]:
    entries = minimal_entries(name)
    entries[0] = (
        "manifest.toml",
        f'[plugin]\nname = "{name}"\nversion = "{version}"\n'.encode(),
    )
    return entries
