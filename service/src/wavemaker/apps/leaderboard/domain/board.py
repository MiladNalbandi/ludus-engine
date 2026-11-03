"""Boards, the places players hold on them, and what a request must be to change either.

What a board is *not* is a record of what happened. A score arrives from a client, and the
service cannot tell a real lap time from an invented one. A leaderboard fed by clients is a
leaderboard of what clients claimed; a game that needs better submits from its own server.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from wavemaker.platform.kernel.storable import unstorable

# The project's own word, safe in a URL without escaping. The same shape the schema checks.
BOARD_ID = re.compile(r"^[a-z0-9_]+$")
MAX_BOARD_ID_LENGTH = 64
MAX_NAME_LENGTH = 255

# A score is a bigint. Negative scores are allowed: golf, a time under par, a net result.
MIN_SCORE = -(2**63)
MAX_SCORE = 2**63 - 1


@dataclass(frozen=True, slots=True)
class Board:
    id: str
    name: str
    descending: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Entry:
    """One player's place. The rank is computed for the read that produced it, never stored:
    a stored rank is wrong for everybody below the next score that changes."""

    player_id: uuid.UUID
    display_name: str | None
    score: int
    rank: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Cursor:
    """The key of the last row a page returned: its score, and the player that breaks ties."""

    score: int
    player_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Page:
    board: Board
    entries: list[Entry]
    total: int
    next: Cursor | None


class LeaderboardError(Exception):
    """A request about a board that was understood and not acted on."""


class InvalidRequest(LeaderboardError):
    """Not a request anybody could make. `pointer` names the field."""

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer


class NoSuchBoard(LeaderboardError):
    """No board by that id in this project."""


class NoSuchPlayer(LeaderboardError):
    """The player is not in this project, or no longer anywhere."""


def is_board_id(value: str) -> bool:
    return len(value) <= MAX_BOARD_ID_LENGTH and BOARD_ID.match(value) is not None


def board_id(value: str) -> str:
    if not is_board_id(value):
        raise InvalidRequest(
            "/boardId",
            f"a board id is lower-case letters, digits and '_', at most "
            f"{MAX_BOARD_ID_LENGTH} characters",
        )
    return value


def board_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequest("/name", "a board needs a name a person can read")
    trimmed = value.strip()
    unusable = unstorable(trimmed)
    if unusable:
        raise InvalidRequest("/name", unusable)
    if len(trimmed) > MAX_NAME_LENGTH:
        raise InvalidRequest("/name", f"a board's name is at most {MAX_NAME_LENGTH} characters")
    return trimmed


def direction(value: object) -> bool:
    """`descending`, which defaults to true: a bigger number is better unless a board says not.
    `"false"` is refused rather than read as true, which is what Python would make of it."""
    if value is None:
        return True
    if not isinstance(value, bool):
        raise InvalidRequest("/descending", "descending is true or false")
    return value


def score_of(value: object) -> int:
    """A whole number a bigint holds. `true` is not a score of one, it is a client bug."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRequest("/score", "a score is a whole number")
    if not MIN_SCORE <= value <= MAX_SCORE:
        raise InvalidRequest("/score", f"a score is between {MIN_SCORE} and {MAX_SCORE}")
    return value
