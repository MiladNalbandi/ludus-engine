"""Waves and levels: what a game client reads, and what an author writes.

The app exposes one `router` to the platform, which mounts it without knowing what is on it.
Two routers sit behind it and the split is deliberate: the public one is anonymous by design,
the admin one is behind a role, and keeping them in separate modules means a new public route
cannot pick up an author's permissions by being written next to one.
"""

from fastapi import APIRouter

from wavemaker.apps.content.adapters.admin import get_wave_store
from wavemaker.apps.content.adapters.admin import router as admin_router
from wavemaker.apps.content.adapters.http import get_wave_repository
from wavemaker.apps.content.adapters.http import router as public_router

router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)

__all__ = ["get_wave_repository", "get_wave_store", "router"]
