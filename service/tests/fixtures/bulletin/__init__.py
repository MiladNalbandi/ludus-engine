"""The fixture plugin's backend: one route, for its editor screen to read.

It is behind an editor's token on purpose. The screen reaches it through the shell's own
request helpers, so the test that opens the screen also proves a plugin's UI calls its backend
as the signed-in author — through the editor's proxy, with the token the shell holds.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from wavemaker.platform.identity.http import requires
from wavemaker.platform.identity.tokens import Role

router = APIRouter(prefix="/api/v1/bulletin")

EDITOR = Depends(requires(Role.EDITOR, Role.ADMIN))


@router.get("/notice", dependencies=[EDITOR])
def notice() -> dict[str, Any]:
    return {
        "title": "Bulletin is installed",
        "body": "This screen arrived in the plugin's ui/ folder. The editor was not rebuilt.",
        "pinned": ["Arrived with plugin install", "Checked against its install record"],
    }
