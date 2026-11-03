"""The plugin package: one archive, `<name>-<version>.wmp`, built from an app folder.

```
inventory-1.0.0.wmp            a zip archive
  manifest.toml                name, version, platform range, permissions
  backend/                     the Python package: __init__.py, domain/, application/, ...
  migrations/                  the app's own Alembic revisions
  ui/                          optional: its screen for the editor, already built
```

**Built the same way every time.** Entries are sorted, every timestamp is the zip format's
earliest, and every file has the same mode, so one folder always makes the same bytes. The
checksum in the registry index is then a fact about the source, not about when it was zipped.

**Read as hostile.** Everything about an archive is checked before a byte of it is written:
every entry name, its type, its size and the total. Refused, with the entry named:

- a path that is absolute, carries a drive letter or a backslash, or has an empty, `.` or `..`
  segment — anything that could resolve outside the directory it is unpacked into;
- a symbolic link, a device, or any entry that is not a plain file or directory;
- an entry outside the four the format allows, a name used twice (in any letter case, since
  the disk may not tell them apart), or an encrypted entry;
- more entries, or more bytes once inflated, than a package may hold. The inflated size is
  counted while it is written, not taken from the archive's own say-so.

Unpacking writes only into a directory it has just created, with files opened for exclusive
creation, so nothing already on the disk is followed or overwritten.
"""

from __future__ import annotations

import io
import re
import stat
import zipfile
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path

from wavemaker.platform.kernel.errors import PackageError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.plugins.loader import MANIFEST_FILE, parse_manifest

SUFFIX = ".wmp"
BACKEND = "backend"
MIGRATIONS = "migrations"
UI = "ui"
TOP_LEVEL = frozenset({MANIFEST_FILE, BACKEND, MIGRATIONS, UI})

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_UNPACKED_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 4096

EPOCH = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o100644
VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]*$")
DRIVE = re.compile(r"^[A-Za-z]:")

SKIPPED_DIRECTORIES = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", "tests"})
SKIPPED_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True, slots=True)
class Package:
    """An archive that has been checked, entry by entry, and the manifest it carries."""

    manifest: AppManifest
    entries: tuple[zipfile.ZipInfo, ...]
    data: bytes


def file_name(manifest: AppManifest) -> str:
    if not VERSION.match(manifest.version):
        raise PackageError(
            f"Version {manifest.version!r} of '{manifest.name}' cannot name a package file. "
            "Use letters, digits, '.', '+', '_' and '-'."
        )
    return f"{manifest.name}-{manifest.version}{SUFFIX}"


def build(app_directory: Path, out_directory: Path) -> Path:
    """Package an app folder: its manifest, its migrations, its ui, and the rest as code."""
    manifest_file = app_directory / MANIFEST_FILE
    if not manifest_file.is_file():
        raise PackageError(f"{app_directory} has no {MANIFEST_FILE}, so it is not an app.")
    manifest = parse_manifest(manifest_file.read_bytes(), source=str(manifest_file))
    if not (app_directory / "__init__.py").is_file():
        raise PackageError(f"{app_directory} has no __init__.py: its code is not a package.")

    entries = sorted(_entries(app_directory), key=lambda pair: pair[0])
    refuse_inconsistent_ui(
        manifest, [name for name, _ in entries], undeclared_folder_allowed=False
    )
    out_directory.mkdir(parents=True, exist_ok=True)
    target = out_directory / file_name(manifest)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, source in entries:
            info = zipfile.ZipInfo(name, date_time=EPOCH)
            info.external_attr = FILE_MODE << 16
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
    target.write_bytes(buffer.getvalue())
    return target


def read(data: bytes) -> Package:
    """Check an archive held in memory, and read its manifest. Nothing touches the disk."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise PackageError(f"The package is {len(data)} bytes; at most {MAX_ARCHIVE_BYTES}.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as broken:
        raise PackageError(f"The package is not a zip archive ({broken}).") from broken

    with archive:
        entries = tuple(archive.infolist())
        _check_entries(entries)
        try:
            manifest_bytes = archive.read(MANIFEST_FILE)
        except KeyError as missing:
            raise PackageError(f"The package has no {MANIFEST_FILE} at its root.") from missing
        except (zipfile.BadZipFile, OSError, EOFError) as broken:
            raise PackageError(f"The package's {MANIFEST_FILE} is corrupt ({broken}).") from broken

    names = {entry.filename for entry in entries}
    if f"{BACKEND}/__init__.py" not in names:
        raise PackageError(f"The package has no {BACKEND}/__init__.py: it carries no code.")

    return Package(
        manifest=parse_manifest(manifest_bytes, source=f"package {MANIFEST_FILE}"),
        entries=entries,
        data=data,
    )


def refuse_inconsistent_ui(
    manifest: AppManifest, names: Collection[str], *, undeclared_folder_allowed: bool
) -> None:
    """`[ui]` names a file the package carries; and, when building, a `ui/` folder is declared.

    A folder with no `[ui]` is refused when an author builds — it is a screen that would never
    appear, with nothing to say why — but accepted at install, because packages built before R8
    carry one and must keep installing. Such a folder is carried and never served.
    """
    has_ui_files = any(name.startswith(f"{UI}/") and not name.endswith("/") for name in names)
    if manifest.ui is None:
        if has_ui_files and not undeclared_folder_allowed:
            raise PackageError(
                f"'{manifest.name}' has a {UI}/ folder but its manifest has no [ui] table. "
                'Declare its entry and interface version: [ui] entry = "module.js", api = 2.'
            )
        return
    if manifest.ui.path not in names:
        raise PackageError(
            f"'{manifest.name}' declares [ui] entry = {manifest.ui.entry!r}, and the package "
            f"carries no {manifest.ui.path}."
        )


def unpack(package: Package, destination: Path) -> None:
    """Write a checked package into `destination`, which must not exist yet."""
    destination.mkdir(parents=False, exist_ok=False)
    root = destination.resolve()
    written = 0
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        for entry in package.entries:
            target = (root / entry.filename).resolve()
            if not target.is_relative_to(root):
                raise PackageError(f"Entry {entry.filename!r} resolves outside the package.")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(entry) as source, target.open("xb") as sink:
                    while chunk := source.read(64 * 1024):
                        written += len(chunk)
                        if written > MAX_UNPACKED_BYTES:
                            raise PackageError(
                                f"The package inflates past {MAX_UNPACKED_BYTES} bytes."
                            )
                        sink.write(chunk)
            except (zipfile.BadZipFile, EOFError) as broken:
                raise PackageError(f"Entry {entry.filename!r} is corrupt ({broken}).") from broken
            target.chmod(0o644)


def _entries(app_directory: Path) -> Iterator[tuple[str, Path]]:
    for path in sorted(app_directory.rglob("*")):
        relative = path.relative_to(app_directory)
        if any(part in SKIPPED_DIRECTORIES or part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink():
            raise PackageError(f"{path} is a symbolic link; a package holds only files.")
        if path.is_dir() or path.suffix in SKIPPED_SUFFIXES:
            continue
        if not path.is_file():
            raise PackageError(f"{path} is not a regular file.")
        top = relative.parts[0]
        if relative.as_posix() == MANIFEST_FILE or top in (MIGRATIONS, UI):
            yield relative.as_posix(), path
        else:
            yield f"{BACKEND}/{relative.as_posix()}", path


def _check_entries(entries: tuple[zipfile.ZipInfo, ...]) -> None:
    if len(entries) > MAX_ENTRIES:
        raise PackageError(f"The package has {len(entries)} entries; at most {MAX_ENTRIES}.")

    seen: set[str] = set()
    declared = 0
    for entry in entries:
        name = entry.filename
        _check_name(name)
        _check_type(entry)
        if entry.flag_bits & 0x1:
            raise PackageError(f"Entry {name!r} is encrypted.")
        folded = name.rstrip("/").casefold()
        if folded in seen:
            raise PackageError(f"Entry {name!r} appears more than once.")
        seen.add(folded)
        declared += entry.file_size
        if declared > MAX_UNPACKED_BYTES:
            raise PackageError(f"The package declares more than {MAX_UNPACKED_BYTES} bytes.")


def _check_name(name: str) -> None:
    if not name or "\\" in name or "\x00" in name or name.startswith("/") or DRIVE.match(name):
        raise PackageError(f"Entry {name!r} is not a relative path inside the package.")
    raw = (name[:-1] if name.endswith("/") else name).split("/")
    if any(part in ("", ".", "..") for part in raw):
        raise PackageError(f"Entry {name!r} walks out of, or around, its directory.")
    if raw[0] not in TOP_LEVEL:
        raise PackageError(
            f"Entry {name!r} is outside what a package holds: "
            f"{', '.join(sorted(TOP_LEVEL))}."
        )
    if raw[0] == MANIFEST_FILE and len(raw) > 1:
        raise PackageError(f"Entry {name!r}: {MANIFEST_FILE} is a file, not a directory.")


def _check_type(entry: zipfile.ZipInfo) -> None:
    mode = entry.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        raise PackageError(f"Entry {entry.filename!r} is a symbolic link.")
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise PackageError(f"Entry {entry.filename!r} is not a plain file or directory.")
    if kind == stat.S_IFDIR and not entry.is_dir():
        raise PackageError(f"Entry {entry.filename!r} claims to be a directory and is not one.")
