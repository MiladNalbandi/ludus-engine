"""Boards and the ranking query, in PostgreSQL.

**The better score is kept by the statement that writes it.** A submission is one upsert whose
`do update` carries the comparison in its `where`, so the read and the write are one operation.
Read-compare-write would lose a better score that arrived in between, and a leaderboard is
written by everybody at once, at the end of a round. The Java did update-then-insert and caught
the insert's unique violation, which in PostgreSQL leaves the transaction aborted: the read it
made next, to say what the board held, could only fail.

**A page is a keyset walk over (score, player_id)**, in the board's direction. The tie-break is
not decoration: scores tie constantly, and a cursor over an order that is not total skips and
repeats rows at every tie. The rows, the rank of the first of them and the board's total come
from one statement, so they describe the same moment.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from wavemaker.apps.leaderboard.domain.board import (
    Board,
    Cursor,
    Entry,
    NoSuchBoard,
    NoSuchPlayer,
)

FOREIGN_KEY_VIOLATION = "23503"
BOARD_COLUMNS = "board_id, name, descending, created_at, updated_at"


class PostgresBoards:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def list_boards(self) -> Sequence[Board]:
        rows = self._session.execute(
            text(f"""
                select {BOARD_COLUMNS} from leaderboard_board
                where project_id = :project order by board_id
            """),
            {"project": self._project},
        ).all()
        return [_board(row) for row in rows]

    def find(self, board_id: str) -> Board | None:
        row = self._session.execute(
            text(f"""
                select {BOARD_COLUMNS} from leaderboard_board
                where project_id = :project and board_id = :board
            """),
            {"project": self._project, "board": board_id},
        ).one_or_none()
        return None if row is None else _board(row)

    def save(self, board_id: str, name: str, descending: bool) -> Board:
        """An upsert, so two first saves of one board both succeed. The Java updated, found no
        row, and inserted, and the second of two concurrent creators got a unique violation."""
        now = datetime.now(UTC)
        row = self._session.execute(
            text(f"""
                insert into leaderboard_board as board
                    (project_id, board_id, name, descending, created_at, updated_at)
                values (:project, :board, :name, :descending, :now, :now)
                on conflict (project_id, board_id) do update
                    set name = excluded.name,
                        descending = excluded.descending,
                        updated_at = excluded.updated_at
                returning {BOARD_COLUMNS}
            """),
            {
                "project": self._project,
                "board": board_id,
                "name": name,
                "descending": descending,
                "now": now,
            },
        ).one()
        self._session.commit()
        return _board(row)

    def delete(self, board_id: str) -> bool:
        removed = self._session.execute(
            text("""
                delete from leaderboard_board where project_id = :project and board_id = :board
                returning board_id
            """),
            {"project": self._project, "board": board_id},
        ).one_or_none()
        self._session.commit()
        return removed is not None

    def submit(self, board_id: str, player: uuid.UUID, score: int) -> Entry:
        try:
            self._session.execute(
                text("""
                    insert into leaderboard_entry as entry
                        (project_id, board_id, player_id, score, updated_at)
                    values (:project, :board, :player, :score, :now)
                    on conflict (project_id, board_id, player_id) do update
                        set score = excluded.score,
                            updated_at = excluded.updated_at
                        -- Only when better, in the board's own direction. An equal score is
                        -- not better, so the time the player first reached it is kept.
                        where case
                            when (select board.descending from leaderboard_board board
                                  where board.project_id = entry.project_id
                                    and board.board_id = entry.board_id)
                            then excluded.score > entry.score
                            else excluded.score < entry.score
                        end
                """),
                {
                    "project": self._project,
                    "board": board_id,
                    "player": player,
                    "score": score,
                    "now": datetime.now(UTC),
                },
            )
            board = self.find(board_id)
            entry = None if board is None else self.entry_of(board, player)
            self._session.commit()
        except DBAPIError as refused:
            self._session.rollback()
            if _sqlstate(refused) == FOREIGN_KEY_VIOLATION:
                if _constraint(refused) == "fk_leaderboard_entry_board":
                    raise NoSuchBoard(f"There is no board '{board_id}'.") from refused
                raise NoSuchPlayer("This player no longer exists.") from refused
            raise
        if board is None or entry is None:
            # Deleted between the write and the read: the board, or the player and their score
            # with them. Either way there is nothing to say the player holds.
            raise NoSuchBoard(f"There is no board '{board_id}'.")
        return entry

    def entry_of(self, board: Board, player: uuid.UUID) -> Entry | None:
        ahead = ">" if board.descending else "<"
        row = self._session.execute(
            text(f"""
                select entry.player_id, entry.score, entry.updated_at, player.display_name,
                    (select count(*) from leaderboard_entry other
                     where other.project_id = entry.project_id
                       and other.board_id = entry.board_id
                       and (other.score, other.player_id) {ahead}
                           (entry.score, entry.player_id)) as ahead
                from leaderboard_entry entry
                join player on player.id = entry.player_id
                    and player.project_id = entry.project_id
                where entry.project_id = :project and entry.board_id = :board
                  and entry.player_id = :player
            """),
            {"project": self._project, "board": board.id, "player": player},
        ).one_or_none()
        return None if row is None else _entry(row, int(row.ahead) + 1)

    def page(self, board: Board, after: Cursor | None, limit: int) -> tuple[list[Entry], int]:
        # Descending: the best is the biggest, and "after" means smaller. Ascending: the mirror.
        order = "desc" if board.descending else "asc"
        beyond = "<" if board.descending else ">"
        ahead = ">" if board.descending else "<"
        keyset = (
            ""
            if after is None
            else f"and (entry.score, entry.player_id) {beyond} (:score, :player)"
        )
        rows = self._session.execute(
            text(f"""
                with shown as (
                    select entry.player_id, entry.score, entry.updated_at
                    from leaderboard_entry entry
                    where entry.project_id = :project and entry.board_id = :board {keyset}
                    order by entry.score {order}, entry.player_id {order}
                    limit :limit
                ),
                head as (
                    select score, player_id from shown
                    order by score {order}, player_id {order}
                    limit 1
                )
                select shown.player_id, shown.score, shown.updated_at, player.display_name,
                    (select count(*) from leaderboard_entry other, head
                     where other.project_id = :project and other.board_id = :board
                       and (other.score, other.player_id) {ahead}
                           (head.score, head.player_id)) as ahead,
                    (select count(*) from leaderboard_entry counted
                     where counted.project_id = :project and counted.board_id = :board) as total
                from shown
                join player on player.id = shown.player_id and player.project_id = :project
                order by shown.score {order}, shown.player_id {order}
            """),
            {
                "project": self._project,
                "board": board.id,
                "limit": limit,
                "score": None if after is None else after.score,
                "player": None if after is None else after.player_id,
            },
        ).all()
        if not rows:
            return [], self._count(board.id)
        first_rank = int(rows[0].ahead) + 1
        return [_entry(row, first_rank + index) for index, row in enumerate(rows)], int(
            rows[0].total
        )

    def _count(self, board_id: str) -> int:
        found = self._session.execute(
            text("""
                select count(*) from leaderboard_entry
                where project_id = :project and board_id = :board
            """),
            {"project": self._project, "board": board_id},
        ).scalar_one()
        return int(found)


def _sqlstate(error: DBAPIError) -> str | None:
    state = getattr(error.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


def _constraint(error: DBAPIError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None)
    return name if isinstance(name, str) else None


def _board(row: Any) -> Board:
    return Board(
        id=row.board_id,
        name=row.name,
        descending=bool(row.descending),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _entry(row: Any, rank: int) -> Entry:
    return Entry(
        player_id=uuid.UUID(str(row.player_id)),
        display_name=row.display_name,
        score=int(row.score),
        rank=rank,
        updated_at=row.updated_at,
    )
