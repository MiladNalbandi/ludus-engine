"""Uploading, listing, deleting and mixing. Every route here is behind a role.

Viewers may list; only editors and administrators may change anything, the same split the
content app makes. Uploads decide what every player downloads, so an unauthenticated write
here would be an unauthenticated change to the game.

**Nothing here reads a whole upload.** The body is fed from the socket through the multipart
parser into the blob store one chunk at a time (`multipart.py`), and the limit is counted as
it goes. A declared `Content-Length` over the limit is refused before a byte is read; a body
with no declared length is cut off at the chunk that crosses it.

**Every refusal is a 4xx and leaves nothing behind:** 415 for a type this service will not
store (SVG as a sprite above all), 413 for too large, 422 for an empty file or a form with no
`file` part, 400 for a body that cannot be read as multipart at all.

Status codes follow what the Java answered — 201 on create, 204 on delete — rather than the
blanket 200 its generated document lists, as the content app does.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from wavemaker.apps.media.adapters.multipart import (
    FRAMING_ALLOWANCE,
    BodyTooLarge,
    MalformedMultipart,
    MissingFile,
    NotMultipart,
    receive_file,
)
from wavemaker.apps.media.adapters.wiring import AdminLibrary, Configured
from wavemaker.apps.media.application.library import EmptyUpload, MediaLibrary, PendingUpload
from wavemaker.apps.media.application.ports import MixFailed, MixTimedOut, MixUnavailable
from wavemaker.apps.media.domain.asset import Asset, AssetKind, parse_id
from wavemaker.apps.media.domain.formats import UnsupportedFormat
from wavemaker.apps.media.domain.mix import MixRefused, read_mix
from wavemaker.platform.identity.http import requires
from wavemaker.platform.identity.tokens import Role
from wavemaker.platform.storage.blobs import BlobTooLarge

router = APIRouter(prefix="/api/v1/admin", tags=["media"])

READER = Depends(requires(Role.VIEWER, Role.EDITOR, Role.ADMIN))
WRITER = Depends(requires(Role.EDITOR, Role.ADMIN))

# A mix request is a filename and a handful of ids. Anything larger is not one.
MAX_MIX_REQUEST = 64 * 1024


def _moment(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _summary(asset: Asset) -> dict[str, Any]:
    """`AudioClipSummary` and `SpriteSummary`, which are the same five fields."""
    return {
        "id": str(asset.id),
        "filename": asset.filename,
        "contentType": asset.content_type,
        "sizeBytes": asset.size_bytes,
        "createdAt": _moment(asset.created_at),
    }


# --- listing -------------------------------------------------------------------------------


@router.get("/audio", dependencies=[READER])
def list_audio_clips(library: AdminLibrary) -> list[dict[str, Any]]:
    """Metadata only; no file is opened."""
    return [_summary(asset) for asset in library.list(AssetKind.AUDIO)]


@router.get("/sprites", dependencies=[READER])
def list_sprites(library: AdminLibrary) -> list[dict[str, Any]]:
    return [_summary(asset) for asset in library.list(AssetKind.SPRITE)]


# --- uploading -----------------------------------------------------------------------------


@router.post("/audio", dependencies=[WRITER], status_code=201)
async def upload_audio_clip(request: Request, library: AdminLibrary) -> dict[str, Any]:
    return _summary(await _upload(AssetKind.AUDIO, request, library))


@router.post("/sprites", dependencies=[WRITER], status_code=201)
async def upload_sprite(request: Request, library: AdminLibrary) -> dict[str, Any]:
    return _summary(await _upload(AssetKind.SPRITE, request, library))


async def _upload(kind: AssetKind, request: Request, library: MediaLibrary) -> Asset:
    max_body = library.limits.of(kind) + FRAMING_ALLOWANCE
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_body:
        # Refused before a byte is read: the client said how much is coming.
        raise HTTPException(status_code=413, detail=_too_large(library.limits.of(kind)))

    pending: PendingUpload | None = None

    def open_sink(filename: str | None, content_type: str | None) -> PendingUpload:
        nonlocal pending
        pending = library.accept(kind, filename, content_type)
        return pending

    try:
        await receive_file(
            request.stream(),
            request.headers.get("content-type"),
            field="file",
            open_sink=open_sink,
            max_body=max_body,
        )
        if pending is None:  # receive_file returns only once a sink was opened; said twice
            raise MissingFile("The form has no 'file' part.")
        return await run_in_threadpool(pending.finish)
    except UnsupportedFormat as refused:
        raise HTTPException(status_code=415, detail=str(refused)) from refused
    except (BlobTooLarge, BodyTooLarge) as too_large:
        raise HTTPException(
            status_code=413, detail=_too_large(library.limits.of(kind))
        ) from too_large
    except NotMultipart as wrong:
        raise HTTPException(status_code=415, detail=str(wrong)) from wrong
    except MalformedMultipart as broken:
        raise HTTPException(status_code=400, detail=str(broken)) from broken
    except (MissingFile, EmptyUpload) as unacceptable:
        raise HTTPException(status_code=422, detail=str(unacceptable)) from unacceptable
    finally:
        # Idempotent, and a no-op once finished: whatever went wrong, no partial file stays.
        if pending is not None:
            pending.abort()


def _too_large(limit: int) -> str:
    return f"The file is larger than the limit of {limit} bytes."


# --- deleting ------------------------------------------------------------------------------


@router.delete("/audio/{asset_id}", dependencies=[WRITER], status_code=204)
def delete_audio_clip(asset_id: str, library: AdminLibrary) -> Response:
    """The clip and its bytes."""
    return _delete(AssetKind.AUDIO, asset_id, library)


@router.delete("/sprites/{asset_id}", dependencies=[WRITER], status_code=204)
def delete_sprite(asset_id: str, library: AdminLibrary) -> Response:
    """Items referring to it are not changed: an item's sprite reference is opaque — it may be
    a URL or an atlas key — so this service has no list of what points at what."""
    return _delete(AssetKind.SPRITE, asset_id, library)


def _delete(kind: AssetKind, raw_id: str, library: MediaLibrary) -> Response:
    asset_id = parse_id(raw_id)
    if asset_id is None or not library.delete(kind, asset_id):
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)


# --- mixing --------------------------------------------------------------------------------


@router.post("/audio/mix", dependencies=[WRITER], status_code=201)
async def mix_audio_clips(
    request: Request,
    library: AdminLibrary,
    settings: Configured,
) -> dict[str, Any]:
    """The result is an ordinary clip afterwards: served, listed and deleted like any upload.

    503 when this service cannot mix — no FFmpeg configured, or the mix ran past its limit and
    was stopped. 422 when the request names something that is not a clip here, or the mixer
    ran and could not make one out of these tracks.
    """
    try:
        body = json.loads(await _bounded_body(request, MAX_MIX_REQUEST))
    except (json.JSONDecodeError, UnicodeDecodeError) as broken:
        raise HTTPException(status_code=400, detail=f"This is not JSON: {broken}") from broken

    try:
        mix = read_mix(body, max_tracks=settings.mix_max_tracks)
        # In a worker thread: copying the inputs and waiting on FFmpeg both block.
        asset = await run_in_threadpool(library.mix, mix)
    except MixRefused as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
    except (MixUnavailable, MixTimedOut) as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable
    except MixFailed as failed:
        raise HTTPException(status_code=422, detail=str(failed)) from failed
    return _summary(asset)


async def _bounded_body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise HTTPException(status_code=413, detail=_too_large(limit))
    return bytes(body)
