"""The registry: a directory of signed archives and one index file that lists them.

```
registry/
  index.json               {"format": 1, "plugins": [ {name, version, file, sha256, key,
                                                       signature}, ... ]}
  inventory-1.0.0.wmp
```

The simplest thing that works, as the design says: a server comes when there are enough
plugins to need searching, and the install command stays the same. A directory can be a mounted
share or a checkout; the installer never reaches a network for it.

The index is not signed and does not need to be. Every entry carries its own signature over
its name, version and checksum, so an edited index can only make an install fail — it cannot
make a different archive verify.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wavemaker.platform.kernel.errors import PackageError
from wavemaker.platform.plugins import package, signing

INDEX_FILE = "index.json"
FORMAT = 1
FIELDS = ("name", "version", "file", "sha256", "key", "signature")


@dataclass(frozen=True, slots=True)
class IndexEntry:
    name: str
    version: str
    file: str
    sha256: str
    key: str
    signature: str


def read_index(registry: Path) -> list[IndexEntry]:
    path = registry / INDEX_FILE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as missing:
        raise PackageError(f"The registry {registry} has no {INDEX_FILE}.") from missing
    except (OSError, ValueError) as broken:
        raise PackageError(f"{path} could not be read as JSON ({broken}).") from broken

    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise PackageError(f"{path} is not a format {FORMAT} plugin index.")
    plugins = document.get("plugins")
    if not isinstance(plugins, list):
        raise PackageError(f"{path} has no list of plugins.")
    return [_entry(item, path) for item in plugins]


def find(registry: Path, name: str, version: str) -> IndexEntry:
    for entry in read_index(registry):
        if entry.name == name and entry.version == version:
            return entry
    raise PackageError(f"The registry {registry} lists no {name}@{version}.")


def archive_of(registry: Path, entry: IndexEntry) -> Path:
    """Where an entry's archive is. The file is a bare name: an index cannot point outside its
    own directory, since whoever can edit the index is exactly who must not choose a path."""
    if (
        Path(entry.file).name != entry.file
        or entry.file in ("", ".", "..")
        or not entry.file.endswith(package.SUFFIX)
    ):
        raise PackageError(f"Index entry {entry.name}@{entry.version} names file {entry.file!r}.")
    return registry / entry.file


def publish(archive: Path, registry: Path, private_key: Path) -> IndexEntry:
    """Sign a package and list it. Publishing a version again replaces its entry."""
    data = archive.read_bytes()
    manifest = package.read(data).manifest
    file_name = package.file_name(manifest)
    sha256 = signing.checksum(data)
    private = signing.load_private(private_key)
    entry = IndexEntry(
        name=manifest.name,
        version=manifest.version,
        file=file_name,
        sha256=sha256,
        key=signing.key_id(private.public_key()),
        signature=signing.sign(private, manifest.name, manifest.version, sha256),
    )

    registry.mkdir(parents=True, exist_ok=True)
    if archive.resolve() != (registry / file_name).resolve():
        shutil.copyfile(archive, registry / file_name)

    entries = read_index(registry) if (registry / INDEX_FILE).exists() else []
    kept = [e for e in entries if (e.name, e.version) != (entry.name, entry.version)]
    _write_index(registry, sorted([*kept, entry], key=lambda e: (e.name, e.version)))
    return entry


def _write_index(registry: Path, entries: list[IndexEntry]) -> None:
    document = {"format": FORMAT, "plugins": [asdict(entry) for entry in entries]}
    staging = registry / f".{INDEX_FILE}.{os.getpid()}"
    staging.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    staging.replace(registry / INDEX_FILE)


def _entry(item: Any, path: Path) -> IndexEntry:
    if not isinstance(item, dict) or not all(isinstance(item.get(f), str) for f in FIELDS):
        raise PackageError(f"{path} has an entry without {', '.join(FIELDS)}: {item!r}")
    return IndexEntry(**{f: item[f] for f in FIELDS})
