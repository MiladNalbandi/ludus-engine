"""AC-1 and AC-3: the package format, built from a real app folder and read as hostile.

Every refusal here is of an archive `package.build` would never write. They are built by hand,
entry by entry, because the unpacker's job is the archive somebody *else* built.
"""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest

import wavemaker.apps.inventory
from tests.integration.plugin_kit import (
    device_entry,
    minimal_entries,
    raw_archive,
    symlink_entry,
    write_app,
)
from wavemaker.platform.kernel.errors import PackageError
from wavemaker.platform.plugins import package

INVENTORY = Path(wavemaker.apps.inventory.__file__).resolve().parent


def names_in(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as opened:
        return opened.namelist()


def test_ac1_the_inventory_folder_builds_into_one_archive_with_the_four_parts(
    tmp_path: Path,
) -> None:
    archive = package.build(INVENTORY, tmp_path)

    assert archive.name == "inventory-1.0.0.wmp"
    names = names_in(archive)
    assert "manifest.toml" in names
    assert "backend/__init__.py" in names
    assert "backend/domain/item.py" in names
    assert "migrations/0001_inventory_tables.py" in names
    assert not [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
    assert all(name.split("/")[0] in package.TOP_LEVEL for name in names)
    assert package.read(archive.read_bytes()).manifest.name == "inventory"


def test_ac1_the_same_folder_always_builds_the_same_bytes(tmp_path: Path) -> None:
    """The registry's checksum is a fact about the source, not about when it was zipped."""
    copy = tmp_path / "inventory"
    shutil.copytree(INVENTORY, copy, ignore=shutil.ignore_patterns("__pycache__"))
    first = package.build(copy, tmp_path / "a").read_bytes()
    os.utime(copy / "__init__.py", (0, 0))
    second = package.build(copy, tmp_path / "b").read_bytes()
    assert first == second
    assert first == package.build(INVENTORY, tmp_path / "c").read_bytes()


def test_ac1_a_ui_folder_travels_with_the_package(tmp_path: Path) -> None:
    folder = write_app(tmp_path / "src", "maps")
    (folder / "ui").mkdir()
    (folder / "ui" / "index.js").write_text("export default {}")
    assert "ui/index.js" in names_in(package.build(folder, tmp_path / "out"))


def test_ac1_a_folder_holding_a_symbolic_link_is_not_built(tmp_path: Path) -> None:
    folder = write_app(tmp_path / "src", "maps")
    (folder / "secrets.py").symlink_to("/etc/hosts")
    with pytest.raises(PackageError) as refused:
        package.build(folder, tmp_path / "out")
    assert "symbolic link" in str(refused.value)


def test_ac3_a_checked_package_unpacks_into_its_own_directory(tmp_path: Path) -> None:
    checked = package.read(raw_archive(minimal_entries("maps")))
    package.unpack(checked, tmp_path / "maps")
    assert (tmp_path / "maps" / "backend" / "__init__.py").is_file()
    assert (tmp_path / "maps" / "manifest.toml").is_file()


@pytest.mark.parametrize(
    "name",
    [
        "../escaped.py",
        "backend/../../escaped.py",
        "backend/../../../tmp/escaped.py",
        "/tmp/escaped.py",
        "/backend/__init__.py",
        "C:/escaped.py",
        "backend\\..\\..\\escaped.py",
        "backend/./hidden.py",
        "backend//double.py",
    ],
)
def test_ac3_a_path_that_could_resolve_outside_the_package_is_refused(
    tmp_path: Path, name: str
) -> None:
    data = raw_archive([*minimal_entries("maps"), (name, b"print('escaped')")])
    with pytest.raises(PackageError) as refused:
        package.read(data)
    assert repr(name)[1:-1] in str(refused.value) or name in str(refused.value)
    assert not list(tmp_path.rglob("escaped.py"))


def test_ac3_unpacking_checks_every_path_again_on_its_own(tmp_path: Path) -> None:
    """The second line: a package that somehow skipped `read`'s checks still cannot write
    outside its directory, because `unpack` resolves every target and refuses one outside."""
    data = raw_archive([*minimal_entries("maps"), ("backend/../../escaped.py", b"x = 1")])
    with zipfile.ZipFile(io.BytesIO(data)) as opened:
        unchecked = package.Package(
            manifest=package.read(raw_archive(minimal_entries("maps"))).manifest,
            entries=tuple(opened.infolist()),
            data=data,
        )
    with pytest.raises(PackageError) as refused:
        package.unpack(unchecked, tmp_path / "maps")
    assert "outside" in str(refused.value)
    assert not list(tmp_path.rglob("escaped.py"))


def test_ac3_a_symbolic_link_is_refused(tmp_path: Path) -> None:
    """A link to /etc unpacked first, and a file written through it second, is the classic
    way an archive writes outside its directory without a single '..' in it."""
    data = raw_archive([*minimal_entries("maps"), symlink_entry("backend/etc", "/etc")])
    with pytest.raises(PackageError) as refused:
        package.read(data)
    assert "symbolic link" in str(refused.value)


def test_ac3_a_device_is_refused() -> None:
    data = raw_archive([*minimal_entries("maps"), device_entry("backend/tty")])
    with pytest.raises(PackageError) as refused:
        package.read(data)
    assert "not a plain file" in str(refused.value)


@pytest.mark.parametrize("name", ["setup.py", "wavemaker/__init__.py", "manifest.toml/x"])
def test_ac3_an_entry_outside_the_four_parts_is_refused(name: str) -> None:
    with pytest.raises(PackageError):
        package.read(raw_archive([*minimal_entries("maps"), (name, b"")]))


def test_ac3_a_name_used_twice_in_any_letter_case_is_refused() -> None:
    """A case-insensitive disk would write the second over the first."""
    data = raw_archive([*minimal_entries("maps"), ("backend/__INIT__.py", b"evil = True")])
    with pytest.raises(PackageError) as refused:
        package.read(data)
    assert "more than once" in str(refused.value)


def test_ac3_an_archive_with_no_manifest_or_no_code_is_refused() -> None:
    with pytest.raises(PackageError):
        package.read(raw_archive([("backend/__init__.py", b"")]))
    with pytest.raises(PackageError):
        package.read(raw_archive([minimal_entries("maps")[0]]))


def test_ac3_bytes_that_are_not_a_zip_are_refused() -> None:
    with pytest.raises(PackageError):
        package.read(b"this is not an archive")


def test_ac3_too_many_entries_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(package, "MAX_ENTRIES", 3)
    entries = [*minimal_entries("maps"), ("backend/a.py", b""), ("backend/b.py", b"")]
    with pytest.raises(PackageError):
        package.read(raw_archive(entries))


def test_ac3_inflated_bytes_are_counted_while_written_not_taken_on_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zip bomb declares a small size and inflates to a large one. The declared total passes
    the first check here; the count kept while writing is what stops it."""
    big = b"0" * 4096
    checked = package.read(raw_archive([*minimal_entries("maps"), ("backend/big.py", big)]))
    monkeypatch.setattr(package, "MAX_UNPACKED_BYTES", 2048)
    with pytest.raises(PackageError) as refused:
        package.unpack(checked, tmp_path / "maps")
    assert "inflates" in str(refused.value)


def test_ac3_unpacking_never_writes_into_a_directory_that_already_exists(tmp_path: Path) -> None:
    (tmp_path / "maps").mkdir()
    checked = package.read(raw_archive(minimal_entries("maps")))
    with pytest.raises(FileExistsError):
        package.unpack(checked, tmp_path / "maps")


def test_ac3_an_encrypted_entry_is_refused() -> None:
    data = bytearray(raw_archive(minimal_entries("maps")))
    # Set the "encrypted" bit on the first entry's local and central headers.
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as opened:
        first = opened.infolist()[0]
    data[first.header_offset + 6] |= 0x1
    central = bytes(data).find(b"PK\x01\x02")
    data[central + 8] |= 0x1
    with pytest.raises(PackageError) as refused:
        package.read(bytes(data))
    assert "encrypted" in str(refused.value)
