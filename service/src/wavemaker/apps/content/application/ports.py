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

from wavemaker.apps.content.domain.document import WaveDocument
from wavemaker.apps.content.domain.level import LevelDraft
from wavemaker.apps.content.domain.wave import (
    LevelSummary,
    PlayableLevel,
    WaveSummary,
)


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


class WaveStore(Protocol):
    """Authoring. Separate from `WaveRepository` because reading and writing content are
    different jobs with different callers: a game client only ever needs the first, and a
    route that holds the smaller port cannot accidentally write."""

    def all_summaries(self) -> Sequence[WaveSummary]:
        """Every wave an author owns, drafts included, in play order."""

    def document(self, wave_id: str) -> bytes | None:
        """The stored bytes of any wave, published or not."""

    def save(self, document: WaveDocument) -> WaveSummary:
        """Create or replace a wave. Publication state is not touched: a save is not a publish."""

    def set_published(self, wave_id: str, published: bool) -> WaveSummary | None:
        """Publish or withdraw one wave; nothing when it does not exist."""

    def delete(self, wave_id: str) -> bool:
        """Remove a wave. False when there was nothing to remove."""

    def next_order(self) -> int:
        """The next free play position, so an author is not asked to guess one."""

    def all_levels(self) -> Sequence[LevelSummary]:
        """Every level, with each wave's publication state."""

    def level(self, level_id: str) -> LevelSummary | None:
        """One level; nothing when it does not exist or the id is not one."""

    def create_level(self, draft: LevelDraft) -> LevelSummary:
        """Store a new, inactive level. Raises `MissingWaves` when a wave is not in this
        project, and `Rejected` when the database refuses the membership for any other
        reason; neither leaves anything stored."""

    def update_level(self, level_id: str, draft: LevelDraft) -> LevelSummary | None:
        """Replace a level's name, description and waves wholesale, keeping its id, its
        creation time and whether it is active. It ends with exactly the new list or exactly
        the old one. Nothing when the level does not exist."""

    def delete_level(self, level_id: str) -> bool:
        """Remove a level and its membership, never its waves. False when it was not there."""

    def activate_level(self, level_id: str) -> LevelSummary | None:
        """Make one level the active one; nothing when it does not exist."""

    def save_all(self, documents: Sequence[WaveDocument]) -> Sequence[WaveSummary]:
        """Save every document or none of them.

        An import is one decision by an author, not a sequence of them. Half a catalogue is
        worse than none: nobody can tell which half arrived without reading the whole thing."""

    def delete_all(self, wave_ids: Sequence[str]) -> int:
        """Delete every one of these waves or none of them, and say how many went.

        Raises `MissingWaves`, naming each id that is not in this project by its position,
        and deletes nothing when it does."""
