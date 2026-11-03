"""Items a project defines, and what each player holds of them.

The first app written plugin-first: as a package that will be installed rather than one that
happens to live in this repository. Everything it needs is inside this folder, and it depends
on nothing but `wavemaker.platform`. Inside the package every import is relative, so the code
does not know where it is installed — moving it out of `wavemaker.apps` changes no line here.
A test checks both, by reading every import in the folder.

The app exposes one `router` to the platform, which mounts it without knowing what is on it.
Players are not here: they are the platform's, and this app knows a player only by the id a
verified token or an editor gives it.
"""

from fastapi import APIRouter

from .adapters.http import admin_router, player_router

router = APIRouter()
router.include_router(player_router)
router.include_router(admin_router)

__all__ = ["router"]
