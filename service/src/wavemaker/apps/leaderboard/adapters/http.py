"""The leaderboard routes: a player's, and an editor's.

**A player may submit their own score, and may not grant themselves currency.** That is the
same trust model applied honestly, not an inconsistency. A forged score is cheating, and a
client-fed leaderboard can always be cheated: the service cannot tell a real lap time from an
invented one, and no credential design changes that. Requiring a server credential to submit
would stop the games that have no server and inconvenience nobody else. A forged grant is
minting, and that is refused. So a leaderboard fed by clients is a leaderboard of what clients
claimed, and the documentation says so; a game that needs better submits from its own server.

The player routes take a board id and never a player id. The score written is always the
caller's, taken from a verified token, so there is no handler that could forget to check that
an id in the request is the caller's own.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from wavemaker.apps.leaderboard.adapters.postgres import PostgresBoards
from wavemaker.apps.leaderboard.application import paging as board_paging
from wavemaker.apps.leaderboard.application.ports import Boards
from wavemaker.apps.leaderboard.domain.board import (
    MAX_SCORE,
    MIN_SCORE,
    Board,
    Cursor,
    Entry,
    InvalidRequest,
    LeaderboardError,
    NoSuchBoard,
    NoSuchPlayer,
    Page,
    board_id,
    board_name,
    direction,
    is_board_id,
    score_of,
)
from wavemaker.platform import paging
from wavemaker.platform.identity.http import CurrentPlayer, Database, moment, requires
from wavemaker.platform.identity.tokens import Role

player_router = APIRouter(prefix="/api/v1/player/leaderboards", tags=["Leaderboards"])
admin_router = APIRouter(prefix="/api/v1/admin/leaderboards", tags=["Leaderboards"])

# Defining boards decides what players compete on, like authoring content. A viewer may not, and
# may not read a board here either, as in the Java, where every /admin/leaderboards route is an
# editor's.
EDITOR = Depends(requires(Role.EDITOR, Role.ADMIN))

BoardId = Annotated[str, Path(alias="boardId")]


def get_boards(db: Database) -> Boards:
    """The request's own session. With no database configured the platform answers 503 first:
    an empty list of boards would be a claim that the project has none."""
    session, project, _ = db
    return PostgresBoards(session, project)


Store = Annotated[Boards, Depends(get_boards)]


def _board_view(board: Board) -> dict[str, Any]:
    return {
        "id": board.id,
        "name": board.name,
        "descending": board.descending,
        "createdAt": moment(board.created_at),
        "updatedAt": moment(board.updated_at),
    }


def _entry_view(entry: Entry) -> dict[str, Any]:
    return {
        "playerId": str(entry.player_id),
        "displayName": entry.display_name,
        "score": entry.score,
        "rank": entry.rank,
        "updatedAt": moment(entry.updated_at),
    }


def _page_view(page: Page) -> dict[str, Any]:
    return {
        "board": _board_view(page.board),
        "entries": [_entry_view(entry) for entry in page.entries],
        "total": page.total,
        "nextCursor": None
        if page.next is None
        else paging.encode_cursor(str(page.next.score), str(page.next.player_id)),
    }


def _cursor(cursor: str | None) -> Cursor | None:
    """The key of the last row of the previous page, or a 422.

    Not the first page, as the Java answered. A client whose cursor was damaged and is quietly
    sent back to the start sees every row twice, and has no way to know it."""
    if cursor is None or not cursor.strip():
        return None
    try:
        score, player = paging.decode_cursor(cursor.strip(), 2)
        parsed = Cursor(score=int(score), player_id=uuid.UUID(player))
    except (paging.BadCursor, ValueError) as broken:
        raise HTTPException(
            status_code=422, detail="/cursor: not a cursor this service issued"
        ) from broken
    if not MIN_SCORE <= parsed.score <= MAX_SCORE:
        # Would reach PostgreSQL as a numeric no bigint compares with, and come back a 500.
        raise HTTPException(status_code=422, detail="/cursor: not a cursor this service issued")
    return parsed


def _existing(boards: Boards, candidate: str) -> Board:
    """The board a path names, or 404 — for an id that cannot be one as for one that is not."""
    board = boards.find(candidate) if is_board_id(candidate) else None
    if board is None:
        raise HTTPException(status_code=404, detail=f"There is no board '{candidate}'.")
    return board


def _page(boards: Boards, candidate: str, cursor: str | None, limit: int | None) -> Page:
    after = _cursor(cursor)
    return board_paging.page(boards, _existing(boards, candidate), after, limit)


# --- a player ---------------------------------------------------------------------------------


@player_router.get("", operation_id="listLeaderboards")
def list_leaderboards(_: CurrentPlayer, boards: Store) -> list[dict[str, Any]]:
    return [_board_view(board) for board in boards.list_boards()]


@player_router.get("/{boardId}", operation_id="getLeaderboardPage")
def get_leaderboard_page(
    candidate: BoardId,
    _: CurrentPlayer,
    boards: Store,
    cursor: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Cursor-paged, deliberately with no page number. A row whose score does not change is
    returned exactly once across a walk; a row whose score changes may move."""
    return _page_view(_page(boards, candidate, cursor, limit))


@player_router.get("/{boardId}/me", operation_id="getOwnLeaderboardEntry")
def get_own_leaderboard_entry(
    candidate: BoardId, caller: CurrentPlayer, boards: Store
) -> dict[str, Any]:
    entry = boards.entry_of(_existing(boards, candidate), caller.player)
    if entry is None:
        raise HTTPException(status_code=404, detail="You have no score on this board.")
    return _entry_view(entry)


@player_router.post("/{boardId}/me", operation_id="submitOwnScore")
def submit_own_score(
    candidate: BoardId, body: dict[str, Any], caller: CurrentPlayer, boards: Store
) -> dict[str, Any]:
    """Always the caller's own score. A `playerId` in the body is not read, so it cannot be
    used to write anybody else's."""
    if not is_board_id(candidate):
        raise HTTPException(status_code=404, detail=f"There is no board '{candidate}'.")
    try:
        score = score_of(body.get("score"))
    except InvalidRequest as invalid:
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid
    try:
        return _entry_view(boards.submit(candidate, caller.player, score))
    except NoSuchBoard as missing:
        raise HTTPException(status_code=404, detail=str(missing)) from missing
    except NoSuchPlayer as gone:
        # The token is valid and the player is gone: 404, as /player/me answers.
        raise HTTPException(status_code=404, detail=str(gone)) from gone


# --- an editor --------------------------------------------------------------------------------


@admin_router.get("", dependencies=[EDITOR], operation_id="listLeaderboardsAsAdmin")
def list_leaderboards_as_admin(boards: Store) -> list[dict[str, Any]]:
    return [_board_view(board) for board in boards.list_boards()]


@admin_router.get("/{boardId}", dependencies=[EDITOR], operation_id="getLeaderboardPageAsAdmin")
def get_leaderboard_page_as_admin(
    candidate: BoardId,
    boards: Store,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """The contract names only `limit` here, and the Java served the first page and nothing
    else while handing back a `nextCursor` that could not be used. The cursor is accepted, so
    an editor can walk the board a player can."""
    return _page_view(_page(boards, candidate, cursor, limit))


@admin_router.put("/{boardId}", dependencies=[EDITOR], operation_id="saveLeaderboard")
def save_leaderboard(candidate: BoardId, body: dict[str, Any], boards: Store) -> dict[str, Any]:
    try:
        board = board_id(candidate)
        name = board_name(body.get("name"))
        descending = direction(body.get("descending"))
    except LeaderboardError as invalid:
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid
    return _board_view(boards.save(board, name, descending))


@admin_router.delete(
    "/{boardId}", dependencies=[EDITOR], status_code=204, operation_id="deleteLeaderboard"
)
def delete_leaderboard(candidate: BoardId, boards: Store) -> Response:
    """204, as the Java answered, though the generated document says 200: springdoc writes the
    default when an annotation says nothing. Its scores go with it, by foreign key."""
    if not is_board_id(candidate) or not boards.delete(candidate):
        raise HTTPException(status_code=404, detail=f"There is no board '{candidate}'.")
    return Response(status_code=204)
