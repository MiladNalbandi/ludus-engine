"""What media needs from the outside, said as interfaces.

Two stores, deliberately: metadata in the database, bytes behind the platform's blob store.
Keeping them apart is what lets a list of forty clips be one query that opens no files, and it
is why nothing here returns a byte array.

The blob port is the platform's (`wavemaker.platform.storage.blobs.BlobStore`), not one of
media's own: every app that keeps an upload needs the same rules, and they live in one place.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from wavemaker.apps.media.domain.asset import Asset, AssetKind


class AssetCatalogue(Protocol):
    def add(self, asset: Asset) -> None: ...

    def list(self, kind: AssetKind) -> Sequence[Asset]:
        """Newest first. Metadata only."""

    def find(self, kind: AssetKind, asset_id: uuid.UUID) -> Asset | None: ...

    def remove(self, kind: AssetKind, asset_id: uuid.UUID) -> bool:
        """False when there was nothing to remove."""


@dataclass(frozen=True, slots=True)
class MixSource:
    """An open stream of one clip's bytes, and how loud it should be. Never a filename."""

    bytes: BinaryIO
    gain_db: float


class MixUnavailable(Exception):
    """This service cannot mix at all, as configured. A 503: the request may be fine."""


class MixTimedOut(Exception):
    """The mixer ran past its limit and was stopped."""


class MixFailed(Exception):
    """The mixer ran and could not produce a usable clip from these tracks."""


class Mixer(Protocol):
    content_type: str

    def mix(self, sources: Sequence[MixSource]) -> AbstractContextManager[BinaryIO]:
        """The mixed clip as a stream, valid until the context closes.

        A stream rather than bytes, for the same reason as everywhere else here: a mix of
        eight long tracks is not something to hold in memory to hand it from one function to
        the next.
        """
