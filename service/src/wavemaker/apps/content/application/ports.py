"""What content needs from storage, said as an interface rather than a table.

`published_catalogue` deliberately returns summaries and no document bodies: it is called on
every client launch, and loading documents to answer it would make the cheapest request in
the system the most expensive one.

Publication is the repository's business, not the caller's. "Which rows may a client see" is
a storage question, and a route that filtered them itself is a route that can forget to.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from wavemaker.apps.content.domain.wave import PlayableLevel, WaveSummary


class WaveRepository(Protocol):
    def published_catalogue(self) -> Sequence[WaveSummary]:
        """Every published wave, summaries only, in play order."""

    def find_published(self, wave_id: str) -> WaveSummary | None:
        """One published wave, or nothing. A draft is nothing."""

    def published_document(self, wave_id: str) -> bytes | None:
        """The stored bytes of one published wave, exactly as they were written."""

    def published_documents(self, wave_ids: Sequence[str]) -> Mapping[str, bytes]:
        """The stored bytes for those ids that are published; the rest are simply absent."""

    def active_level(self) -> PlayableLevel | None:
        """The level being played, or nothing when none is active."""
