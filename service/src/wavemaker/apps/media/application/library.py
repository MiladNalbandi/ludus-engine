"""Uploading, listing, serving, deleting and mixing audio and sprites.

The two halves of an asset — its row and its bytes — can come apart, so both directions are
handled rather than assumed:

- **Bytes first, then the row.** A row that is never written leaves bytes nobody can name;
  the reverse would be a row that serves a 404. If the row fails, the bytes are removed.
- **Deleting is the row first, then the bytes.** A clip nobody can find is better than bytes
  nobody owns, and either half failing leaves the service answering honestly.
- **A row whose bytes are gone is a missing asset**, served as a 404 rather than a 500.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO

from wavemaker.apps.media.application.ports import (
    AssetCatalogue,
    Mixer,
    MixFailed,
    MixSource,
    MixUnavailable,
)
from wavemaker.apps.media.domain.asset import Asset, AssetKind, display_name
from wavemaker.apps.media.domain.formats import accept_content, accept_declared
from wavemaker.apps.media.domain.mix import MixRefused, MixRequest
from wavemaker.platform.storage.blobs import BlobStore, BlobTooLarge, BlobWriter

CHUNK = 64 * 1024


class EmptyUpload(Exception):
    """A file part with nothing in it."""


@dataclass(frozen=True, slots=True)
class Limits:
    audio_bytes: int
    sprite_bytes: int

    def of(self, kind: AssetKind) -> int:
        return self.audio_bytes if kind is AssetKind.AUDIO else self.sprite_bytes


class PendingUpload:
    """An upload between its first byte and its row. Fed chunks; finished or aborted once."""

    def __init__(
        self,
        library: MediaLibrary,
        kind: AssetKind,
        asset_id: uuid.UUID,
        filename: str,
        declared: str,
        writer: BlobWriter,
    ) -> None:
        self._library = library
        self._kind = kind
        self._id = asset_id
        self._filename = filename
        self._declared = declared
        self._writer = writer

    def write(self, chunk: bytes) -> None:
        self._writer.write(chunk)

    def finish(self) -> Asset:
        try:
            if self._writer.written == 0:
                raise EmptyUpload("The uploaded file was empty.")
            # From the bytes that arrived, before they are made visible under their id.
            content_type = accept_content(self._kind, self._declared, self._writer.head)
            stored = self._writer.commit()
        except BaseException:
            self._writer.abort()
            raise

        asset = Asset(
            id=self._id,
            kind=self._kind,
            filename=self._filename,
            content_type=content_type,
            size_bytes=stored.size,
            sha256=stored.sha256,
            created_at=self._library.now(),
        )
        try:
            self._library.catalogue.add(asset)
        except BaseException:
            self._library.blobs[self._kind].delete(self._id)
            raise
        return asset

    def abort(self) -> None:
        self._writer.abort()


class MediaLibrary:
    def __init__(
        self,
        catalogue: AssetCatalogue,
        blobs: Mapping[AssetKind, BlobStore],
        limits: Limits,
        mixer: Mixer | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.catalogue = catalogue
        self.blobs = blobs
        self.limits = limits
        self.mixer = mixer
        self.now = now

    def accept(self, kind: AssetKind, filename: str | None, declared: str | None) -> PendingUpload:
        """Start an upload. The label is checked before a byte is written; the bytes are checked
        when it finishes. The id is generated here and nowhere else."""
        content_type = accept_declared(kind, declared)
        asset_id = uuid.uuid4()
        writer = self.blobs[kind].begin(asset_id, limit=self.limits.of(kind))
        return PendingUpload(self, kind, asset_id, display_name(filename), content_type, writer)

    def list(self, kind: AssetKind) -> Sequence[Asset]:
        return self.catalogue.list(kind)

    def find(self, kind: AssetKind, asset_id: uuid.UUID) -> Asset | None:
        return self.catalogue.find(kind, asset_id)

    def open(self, kind: AssetKind, asset_id: uuid.UUID) -> BinaryIO | None:
        """The bytes of an asset this project has, or nothing. The caller closes the stream."""
        if self.catalogue.find(kind, asset_id) is None:
            return None
        return self.blobs[kind].open(asset_id)

    def delete(self, kind: AssetKind, asset_id: uuid.UUID) -> bool:
        if not self.catalogue.remove(kind, asset_id):
            return False
        self.blobs[kind].delete(asset_id)
        return True

    def mix(self, request: MixRequest) -> Asset:
        """Mix existing clips into a new one, which is an ordinary clip afterwards.

        Every track is resolved through this project's catalogue first, so a clip from
        elsewhere cannot be mixed in and a missing one is named before anything runs. The
        mixer is handed open streams and gains — never an id, a filename or a path.
        """
        if self.mixer is None:
            raise MixUnavailable(
                "Mixing is off on this service: set WAVEMAKER_MEDIA_FFMPEG_BINARY to the "
                "absolute path of an ffmpeg binary to turn it on."
            )

        # Every stream opened here is closed here, including on the refusal path. Without
        # this, a request naming one missing clip among five leaks four open files.
        with ExitStack() as opened:
            sources = []
            for index, track in enumerate(request.tracks):
                stream = self.open(AssetKind.AUDIO, track.clip_id)
                if stream is None:
                    raise MixRefused(f"/tracks/{index}", f"no clip '{track.clip_id}' here")
                sources.append(MixSource(bytes=opened.enter_context(stream), gain_db=track.gain_db))

            with self.mixer.mix(sources) as mixed:
                upload = self.accept(AssetKind.AUDIO, request.filename, self.mixer.content_type)
                try:
                    while chunk := mixed.read(CHUNK):
                        upload.write(chunk)
                except BlobTooLarge as too_large:
                    upload.abort()
                    raise MixFailed(
                        f"The mix is larger than a clip may be ({too_large.limit} bytes)."
                    ) from too_large
                except BaseException:
                    upload.abort()
                    raise
                return upload.finish()
