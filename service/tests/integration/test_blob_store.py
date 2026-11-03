"""AC-5, AC-6 and AC-9: bytes on disk, addressed by an id this service generated.

The store is the only code that turns an id into a path, so it is the only place a path can
escape the configured directory, and the only place a half-written upload can be mistaken for
a whole one. Both are proved here rather than assumed.
"""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from pathlib import Path

import pytest

from wavemaker.platform.kernel.errors import ConfigurationError
from wavemaker.platform.storage.blobs import BlobTooLarge, FilesystemBlobs, ensure_writable


def store(root: Path) -> FilesystemBlobs:
    return FilesystemBlobs(ensure_writable(root), "media-audio")


@pytest.mark.ac("AC-6")
def test_ac6_bytes_go_under_the_namespace_named_by_the_id(tmp_path: Path) -> None:
    blobs = store(tmp_path)
    blob = uuid.uuid4()
    writer = blobs.begin(blob, limit=1024)
    writer.write(b"hello ")
    writer.write(b"world")
    stored = writer.commit()

    assert stored.size == 11
    assert stored.sha256 == hashlib.sha256(b"hello world").hexdigest()
    assert (tmp_path / "media-audio" / str(blob)).read_bytes() == b"hello world"


@pytest.mark.ac("AC-6")
@pytest.mark.parametrize("not_an_id", ["../../etc/passwd", "a/b", str(uuid.uuid4()), 7])
def test_ac6_only_a_uuid_can_name_a_blob(tmp_path: Path, not_an_id: object) -> None:
    """Even a string that *is* a UUID is refused: the type is the guarantee, and a caller that
    passes text has skipped the one parse that makes the path safe."""
    blobs = store(tmp_path)
    with pytest.raises(TypeError):
        blobs.begin(not_an_id, limit=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        blobs.open(not_an_id)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        blobs.delete(not_an_id)  # type: ignore[arg-type]


@pytest.mark.ac("AC-6")
@pytest.mark.parametrize("namespace", ["", "..", "a/b", "../escape", "UPPER", "with space"])
def test_ac6_a_namespace_cannot_be_a_path(tmp_path: Path, namespace: str) -> None:
    with pytest.raises(ValueError):
        FilesystemBlobs(tmp_path, namespace)


@pytest.mark.ac("AC-5")
def test_ac5_writing_past_the_limit_is_refused_and_leaves_nothing(tmp_path: Path) -> None:
    blobs = store(tmp_path)
    writer = blobs.begin(uuid.uuid4(), limit=10)
    writer.write(b"12345")
    with pytest.raises(BlobTooLarge):
        writer.write(b"678901")
    writer.abort()
    assert list((tmp_path / "media-audio").iterdir()) == []


@pytest.mark.ac("AC-5")
def test_ac5_an_upload_that_is_never_committed_cannot_be_opened(tmp_path: Path) -> None:
    """A half-written file is written beside its name, never at it. A reader that found it at
    its name would serve a truncated clip as if it were whole."""
    blobs = store(tmp_path)
    blob = uuid.uuid4()
    writer = blobs.begin(blob, limit=1024)
    writer.write(b"partial")
    assert blobs.open(blob) is None
    writer.abort()
    assert list((tmp_path / "media-audio").iterdir()) == []


def test_the_writer_remembers_the_first_bytes_for_sniffing(tmp_path: Path) -> None:
    writer = store(tmp_path).begin(uuid.uuid4(), limit=1 << 20)
    for _ in range(100):
        writer.write(b"ab")
    assert writer.head.startswith(b"abab")
    assert 32 <= len(writer.head) <= 200
    writer.abort()


def test_open_streams_and_delete_removes(tmp_path: Path) -> None:
    blobs = store(tmp_path)
    blob = uuid.uuid4()
    writer = blobs.begin(blob, limit=1024)
    writer.write(b"bytes")
    writer.commit()

    opened = blobs.open(blob)
    assert opened is not None
    with opened:
        assert opened.read() == b"bytes"
    assert blobs.delete(blob) is True
    assert blobs.delete(blob) is False
    assert blobs.open(blob) is None


@pytest.mark.ac("AC-9")
def test_ac9_a_directory_that_cannot_be_written_stops_the_start(tmp_path: Path) -> None:
    """At startup, while somebody is watching the deploy — not at the first upload."""
    if os.geteuid() == 0:
        pytest.skip("root can write to a read-only directory, so there is nothing to refuse")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(ConfigurationError, match="WAVEMAKER_BLOB_DIRECTORY"):
            ensure_writable(locked)
    finally:
        locked.chmod(stat.S_IRWXU)


@pytest.mark.ac("AC-9")
def test_ac9_a_path_that_is_a_file_stops_the_start(tmp_path: Path) -> None:
    occupied = tmp_path / "a-file"
    occupied.write_text("not a directory")
    with pytest.raises(ConfigurationError, match="WAVEMAKER_BLOB_DIRECTORY"):
        ensure_writable(occupied)
