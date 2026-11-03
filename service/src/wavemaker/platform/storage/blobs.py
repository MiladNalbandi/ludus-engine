"""Uploaded bytes on a filesystem, addressed by a UUID this service generated.

Carried over from the Java's `FilesystemBlobs`, which was extracted from the audio store when
sprites needed the same thing. The rules are the ones learned there:

- **Written beside the name and moved into place.** Bytes go to `<id>.partial` and are renamed
  to `<id>` only once they are whole, so a failed or interrupted upload can never be served as
  if it were complete.
- **A chunk at a time.** Nothing here ever holds a whole file. The writer is fed chunks and
  counts them against a limit as they arrive, so an oversized upload is refused at the byte
  that crosses the limit rather than after it has filled the disk.
- **Only a UUID names a file.** Not a string that happens to look like one: the type is the
  guarantee, and a caller that passes text has skipped the parse that makes the path safe.
  The resolved path is checked against the directory anyway, because "cannot escape" is a
  claim worth making the code state.
- **One namespace per kind of thing**, so audio and sprites cannot end up in each other's
  directory by accident.
- **Checked at startup**, not at the first upload. A missing or read-only directory is a
  deployment mistake, and the useful moment to find out is while somebody is watching.

Standard library only, so the core's storage port carries no framework with it.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from wavemaker.platform.kernel.errors import ConfigurationError, PlatformError

SETTING = "WAVEMAKER_BLOB_DIRECTORY"

# Enough for any format check that looks at magic numbers. Kept by the writer as the bytes go
# past, so checking what a file is never means opening it again.
HEAD_BYTES = 64

NAMESPACE = re.compile(r"^[a-z][a-z0-9-]*$")
PARTIAL_SUFFIX = ".partial"


class BlobTooLarge(PlatformError):
    """More bytes arrived than the caller allowed."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"larger than the limit of {limit} bytes")
        self.limit = limit


@dataclass(frozen=True, slots=True)
class StoredBlob:
    """What was actually written: counted and hashed as it went, never declared."""

    size: int
    sha256: str
    head: bytes


class BlobWriter(Protocol):
    @property
    def written(self) -> int: ...

    @property
    def head(self) -> bytes: ...

    def write(self, chunk: bytes) -> None:
        """Append a chunk. Raises `BlobTooLarge` at the chunk that crosses the limit."""

    def commit(self) -> StoredBlob:
        """Make the bytes visible under their id."""

    def abort(self) -> None:
        """Throw away whatever was written. Safe to call more than once, or after a commit."""


class BlobStore(Protocol):
    def begin(self, blob_id: uuid.UUID, *, limit: int) -> BlobWriter: ...

    def open(self, blob_id: uuid.UUID) -> BinaryIO | None:
        """An open stream for the caller to drain and close, or nothing."""

    def delete(self, blob_id: uuid.UUID) -> bool:
        """False when there was nothing to delete."""


def ensure_writable(root: Path) -> Path:
    """The configured directory, created if need be and proved writable, or a refusal.

    Proved by writing to it rather than by `os.access`, which answers for the real uid and is
    wrong under a volume mounted with other permissions — the exact case worth catching.
    """
    directory = root.expanduser().resolve()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".probe-"):
            pass
    except OSError as refused:
        raise ConfigurationError(
            f"{SETTING} is {directory}, and this process cannot write there ({refused}). "
            "Uploaded files are written to this directory rather than into the database; it "
            "has to exist, be a directory, and be writable by the user the service runs as. "
            "Under Docker an empty named volume takes the mount point's owner, and a path "
            "Docker has to create itself is owned by root."
        ) from refused
    return directory


class FilesystemBlobs:
    """One namespace of blobs: `<root>/<namespace>/<uuid>`."""

    def __init__(self, root: Path, namespace: str) -> None:
        if not NAMESPACE.match(namespace):
            raise ValueError(
                f"'{namespace}' is not a blob namespace. Use lower-case letters, digits and "
                "'-', starting with a letter."
            )
        self._directory = root / namespace
        self._directory.mkdir(exist_ok=True)

    def begin(self, blob_id: uuid.UUID, *, limit: int) -> BlobWriter:
        return _FileWriter(self._path(blob_id), limit)

    def open(self, blob_id: uuid.UUID) -> BinaryIO | None:
        try:
            return self._path(blob_id).open("rb")
        except (FileNotFoundError, IsADirectoryError):
            return None

    def delete(self, blob_id: uuid.UUID) -> bool:
        try:
            self._path(blob_id).unlink()
        except FileNotFoundError:
            return False
        return True

    def _path(self, blob_id: uuid.UUID) -> Path:
        if not isinstance(blob_id, uuid.UUID):
            raise TypeError(f"a blob is named by a uuid.UUID, not {type(blob_id).__name__}")
        # A UUID's text is hex and hyphens, so this cannot leave the directory. Checked anyway.
        path = self._directory / str(blob_id)
        if path.parent != self._directory:
            raise ValueError(f"blob {blob_id} resolved outside its directory")
        return path


class _FileWriter:
    def __init__(self, target: Path, limit: int) -> None:
        self._target = target
        self._partial = target.with_name(target.name + PARTIAL_SUFFIX)
        self._limit = limit
        self._hash = hashlib.sha256()
        self._written = 0
        self._head = b""
        self._done = False
        # "x": an id is fresh, so something already there is a bug, not a file to overwrite.
        self._file: BinaryIO = self._partial.open("xb")

    @property
    def written(self) -> int:
        return self._written

    @property
    def head(self) -> bytes:
        return self._head

    def write(self, chunk: bytes) -> None:
        if self._written + len(chunk) > self._limit:
            raise BlobTooLarge(self._limit)
        if len(self._head) < HEAD_BYTES:
            self._head += chunk[: HEAD_BYTES - len(self._head)]
        self._file.write(chunk)
        self._hash.update(chunk)
        self._written += len(chunk)

    def commit(self) -> StoredBlob:
        self._file.flush()
        # Durable before it is visible. A rename that reaches the disk before the bytes do is
        # a whole-looking file of zeros after a power cut.
        os.fsync(self._file.fileno())
        self._file.close()
        os.replace(self._partial, self._target)
        self._done = True
        return StoredBlob(size=self._written, sha256=self._hash.hexdigest(), head=self._head)

    def abort(self) -> None:
        if self._done:
            return
        self._done = True
        self._file.close()
        # Already failing; a leftover .partial is a smaller problem than losing the cause.
        with contextlib.suppress(FileNotFoundError):
            self._partial.unlink()
