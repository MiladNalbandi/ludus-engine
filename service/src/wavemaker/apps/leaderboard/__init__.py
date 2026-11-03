"""Leaderboards: boards a project defines, one score per player per board, and keyset pages.

The app exposes one `router` to the platform, which mounts it without knowing what is on it.
Players are the platform's; this app knows a player only by the id a verified token gives it.
"""

from fastapi import APIRouter

from wavemaker.apps.leaderboard.adapters.http import admin_router, get_boards, player_router

router = APIRouter()
router.include_router(player_router)
router.include_router(admin_router)

__all__ = ["get_boards", "router"]
