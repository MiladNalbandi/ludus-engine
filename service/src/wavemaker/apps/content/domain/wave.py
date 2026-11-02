"""What a wave is, to everything except the database and the web.

A summary is a wave's indexed fields; the document itself is separate bytes, fetched on its
own. That split is the whole reason caching works here: a client polls cheap summaries and
only pulls a document when its tag moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
