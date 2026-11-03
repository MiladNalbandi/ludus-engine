"""A page of a board, and the cursor for the next one.

What "stable" means here is stated precisely, because the alternative is implying more than is
true. **A row whose score does not change is returned exactly once across a walk** — never
skipped, never repeated — however many other scores are written while the walk goes on. A row
whose score *does* change moves: it may be seen twice, or not at all. That is not a flaw to be
fixed; it is what a live ranking is. An offset-paged board gives neither guarantee.
"""

from __future__ import annotations

from wavemaker.apps.leaderboard.application.ports import Boards
from wavemaker.apps.leaderboard.domain.board import Board, Cursor, Page
from wavemaker.platform import paging

ENTRIES_PER_PAGE = 20
MOST_ENTRIES_PER_PAGE = 200


def page(boards: Boards, board: Board, after: Cursor | None, limit: int | None) -> Page:
    size = paging.page_size(limit, default=ENTRIES_PER_PAGE, maximum=MOST_ENTRIES_PER_PAGE)
    # One more than asked for, so whether there is a next page needs no second query.
    found, total = boards.page(board, after, size + 1)
    entries = found[:size]
    last = entries[-1] if len(found) > size else None
    return Page(
        board=board,
        entries=entries,
        total=total,
        next=None if last is None else Cursor(score=last.score, player_id=last.player_id),
    )
