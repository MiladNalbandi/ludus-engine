"""Audio clips and sprites: uploaded by an editor, streamed to anybody.

Metadata lives in PostgreSQL; the bytes live on the filesystem behind the platform's blob
store. The app exposes one `router` to the platform, built from a public router that is
anonymous by design and an admin one that is behind a role, kept in separate modules for the
same reason as in the content app: a new public route cannot pick up an author's permissions
by being written next to one.

`media_settings` is exported so a deployment, or a test, can replace the settings it reads.
"""

from fastapi import APIRouter

from wavemaker.apps.media.adapters.admin import router as admin_router
from wavemaker.apps.media.adapters.http import router as public_router
from wavemaker.apps.media.adapters.settings import media_settings

router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)

__all__ = ["media_settings", "router"]
