"""What a wave is, to everything except the database and the web.

A summary is a wave's indexed fields; the document itself is separate bytes, fetched on its
own. That split is the whole reason caching works here: a client polls cheap summaries and
only pulls a document when its tag moved.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from wavemaker.platform.kernel.errors import PlatformError


class Rejected(PlatformError):
    """A request that was read and is not acceptable.

    The message starts with a JSON Pointer to the field an author has to change — `/name`,
    `/waves/2` — because "the request is invalid" is not something anybody can fix.
    """


class MissingWaves(Rejected):
    """Waves named in a request that this project does not have, each with its position.

    Every one of them, not the first: an author fixing a list of twenty should not learn about
    the problems one round trip at a time.
    """

    def __init__(self, root: str, missing: Sequence[tuple[int, str]]) -> None:
        self.missing = list(missing)
        super().__init__(
            "; ".join(
                f"{root}/{index}: there is no wave '{wave_id}' in this project"
                for index, wave_id in self.missing
            )
        )


@dataclass(frozen=True, slots=True)
class WaveSummary:
    """A wave's indexed fields. Frozen: a summary read from storage is a fact, not a draft."""

    id: str
    name: str
    order: int
    schema_version: int
    published: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PlayableLevel:
    """A level and the waves it names, in the order it names them.

    `wave_ids` holds every wave the level was authored with, including drafts. Which of those
    a client may see is decided when the level is served, not here — a level that quietly
    dropped its drafts could never show an editor "2 of 3 reach players".
    """

    id: str
    name: str
    wave_ids: list[str]


@dataclass(frozen=True, slots=True)
class LevelMember:
    """One wave's place in a level, and whether players will actually receive it.

    `published` is carried here rather than looked up by whoever renders the level, because
    "2 of 3 reach players" is the single most useful thing an author can be told and it must
    not depend on the caller remembering to ask.
    """

    wave_id: str
    published: bool


@dataclass(frozen=True, slots=True)
class LevelSummary:
    """A level as an author sees it: every wave it names, drafts included."""

    id: str
    name: str
    description: str | None
    active: bool
    waves: list[LevelMember]
    created_at: datetime
    updated_at: datetime
