"""Progression: XP, the project's curve, the stage one implies on the other, and rewards.

The app exposes one `router` to the platform, which mounts it without knowing what is on it.
A reward's currency goes through the platform's currency port rather than to the economy app,
which this app may not import.
"""

from fastapi import APIRouter

from wavemaker.apps.progression.adapters.http import (
    admin_router,
    curve_router,
    get_progression,
    player_router,
)

router = APIRouter()
router.include_router(curve_router)
router.include_router(player_router)
router.include_router(admin_router)

__all__ = ["get_progression", "router"]
