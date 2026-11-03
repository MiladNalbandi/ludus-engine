"""What the R5 tests share: a small plugin written to disk, a publisher with a key, and a way to
build the hostile archives a real publisher never would.

Plain functions and one small class rather than fixtures, so each test says what it runs
against without a reader having to open a conftest.
"""

from __future__ import annotations

import io
import json
import stat
import textwrap
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from wavemaker.platform.plugins import index, package, signing

ROUTER = """
from fastapi import APIRouter

router = APIRouter(prefix="{prefix}")


@router.get("/hello")
def hello() -> dict[str, str]:
    return {{"app": "{name}"}}
"""


def write_app(
    root: Path,
    name: str,
    *,
    version: str = "1.0.0",
    requires_platform: str = ">=0.1",
    permissions: str = "",
    code: str | None = None,
    prefix: str | None = None,
    migrations: dict[str, str] | None = None,
    extra_plugin: str = "",
) -> Path:
    """An app folder as an author has it: manifest.toml, an __init__.py, maybe migrations."""
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "manifest.toml").write_text(
        f'[plugin]\nname = "{name}"\nversion = "{version}"\n'
        f'requires_platform = "{requires_platform}"\n{extra_plugin}\n{permissions}\n'
    )
    route_prefix = prefix if prefix is not None else f"/api/v1/{name}"
    (folder / "__init__.py").write_text(
        textwrap.dedent(code) if code is not None else ROUTER.format(prefix=route_prefix, name=name)
    )
    if migrations:
        (folder / "migrations").mkdir()
        for file_name, body in migrations.items():
            (folder / "migrations" / file_name).write_text(textwrap.dedent(body))
    return folder


def revision(body: str, *, revision_id: str = "0001", down: str | None = None) -> str:
    """An Alembic revision file whose upgrade executes `body`, one SQL statement per line."""
    statements = "\n".join(
        f"    op.execute({line.strip()!r})" for line in body.strip().splitlines() if line.strip()
    )
    return (
        "from alembic import op\n\n"
        f"revision = {revision_id!r}\n"
        f"down_revision = {down!r}\n"
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade() -> None:\n"
        f"{statements}\n\n\n"
        "def downgrade() -> None:\n"
        "    pass\n"
    )


@dataclass
class Publisher:
    """One signing key, a registry it publishes to, and a directory that trusts it."""

    root: Path

    def __post_init__(self) -> None:
        self.private_key = self.root / "keys" / "publisher.pem"
        self.key_id = signing.generate(self.private_key)
        self.registry = self.root / "registry"
        self.trusted = self.root / "trusted"
        self.trusted.mkdir(parents=True)
        (self.trusted / "publisher.pub").write_bytes(
            self.private_key.with_suffix(".pub").read_bytes()
        )
        self.plugins = self.root / "plugins"

    def publish_folder(self, folder: Path) -> index.IndexEntry:
        archive = package.build(folder, self.root / "built")
        return index.publish(archive, self.registry, self.private_key)

    def publish_bytes(self, name: str, version: str, data: bytes) -> index.IndexEntry:
        """Sign and list an archive exactly as given — how a hostile archive gets a genuine
        signature: a compromised build, or a publisher's mistake. The unpacker must still
        refuse it, since a signature says who sent a package, not that it is safe."""
        self.registry.mkdir(parents=True, exist_ok=True)
        file_name = f"{name}-{version}{package.SUFFIX}"
        (self.registry / file_name).write_bytes(data)
        sha256 = signing.checksum(data)
        private = signing.load_private(self.private_key)
        entry = index.IndexEntry(
            name=name,
            version=version,
            file=file_name,
            sha256=sha256,
            key=self.key_id,
            signature=signing.sign(private, name, version, sha256),
        )
        entries = index.read_index(self.registry) if (self.registry / "index.json").exists() else []
        document = {
            "format": 1,
            "plugins": [asdict(e) for e in entries if (e.name, e.version) != (name, version)]
            + [asdict(entry)],
        }
        (self.registry / "index.json").write_text(json.dumps(document))
        return entry

    def rewrite_index(self, **changes: str) -> None:
        """Edit every entry of the index, as whoever controls the registry directory could."""
        document = json.loads((self.registry / "index.json").read_text())
        for entry in document["plugins"]:
            entry.update(changes)
        (self.registry / "index.json").write_text(json.dumps(document))


def manifest_text(name: str, version: str = "1.0.0", permissions: str = "") -> str:
    return (
        f'[plugin]\nname = "{name}"\nversion = "{version}"\nrequires_platform = ">=0.1"\n'
        f"{permissions}\n"
    )


Entry = tuple[str | zipfile.ZipInfo, bytes]


def raw_archive(entries: list[Entry]) -> bytes:
    """A zip with exactly these entries, including ones `package.build` would never write."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def minimal_entries(name: str) -> list[Entry]:
    return [
        ("manifest.toml", manifest_text(name).encode()),
        ("backend/__init__.py", ROUTER.format(prefix=f"/api/v1/{name}", name=name).encode()),
    ]


def symlink_entry(name: str, target: str) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info, target.encode()


def device_entry(name: str) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFCHR | 0o644) << 16
    return info, b""
