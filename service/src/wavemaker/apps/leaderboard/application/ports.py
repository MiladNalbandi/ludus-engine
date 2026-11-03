"""What leaderboards need from storage, said as an interface rather than a table.

As with the economy, there is no in-memory implementation. The two rules this port exists
for — a better score is never lost to a worse one arriving at the same moment, and a walk
returns each unchanged row exactly once — are kept by PostgreSQL, and a fake would be a second
implementation of exactly those rules, passing tests the real one might fail.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from wavemaker.apps.leaderboard.domain.board import Board, Cursor, Entry


class Boards(Protocol):
    def list_boards(self) -> Sequence[Board]:
        """Every board in this project, by id."""

    def find(self, board_id: str) -> Board | None: ...

    def save(self, board_id: str, name: str, descending: bool) -> Board:
        """Create the board, or replace its name and direction. Its scores stay."""

    def delete(self, board_id: str) -> bool:
        """Remove the board and its scores. False when there was no such board."""

    def submit(self, board_id: str, player: uuid.UUID, score: int) -> Entry:
        """Keep the better of `score` and the player's current one, in the board's direction,
        and return where the player now stands.

        Raises `NoSuchBoard` and `NoSuchPlayer`."""

    def entry_of(self, board: Board, player: uuid.UUID) -> Entry | None: ...

    def page(self, board: Board, after: Cursor | None, limit: int) -> tuple[list[Entry], int]:
        """Up to `limit` entries after `after`, in rank order, and how many the board holds.

        Both from one statement, so the ranks and the total agree with the rows."""
