"""Serving audio and sprites to a game client. Anonymous by design: they ship in every copy.

**Streamed.** The response is fed from the open file 64 KiB at a time, so a request costs a
buffer rather than a copy of the file — ten players starting a level at once is ten buffers.
The generator closes the file whatever happens, so a client that disconnects mid-download
cannot leak a file handle.

**Cached immutably, and tagged.** An asset never changes under its id — a new upload is a new
id — so it is cached for a year with `immutable`. It also carries an ETag, the SHA-256 of its
bytes, so a client that revalidates anyway gets a 304, the same way the content app answers.

**Served as what it was checked to be.** `nosniff`, so a browser uses the type the upload was
accepted under and never guesses a document out of it, and a `sandbox` policy so that even if
one were rendered it could run nothing on this origin.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import StreamingResponse

from wavemaker.apps.media.adapters.wiring import PublicLibrary
from wavemaker.apps.media.domain.asset import AssetKind, parse_id
from wavemaker.apps.media.domain.formats import AUDIO_TYPES, IMAGE_TYPES
from wavemaker.platform.http.etag import matches
from wavemaker.platform.http.etag import quote as quote_tag

router = APIRouter(prefix="/api/v1/public", tags=["media"])

CHUNK = 64 * 1024
# A year. Immutable content addressed by a random id cannot go stale.
IMMUTABLE = "public, max-age=31536000, immutable"

IfNoneMatch = Annotated[str | None, Header(alias="If-None-Match")]


@router.get("/audio/{asset_id}")
def stream_audio_clip(
    asset_id: str, library: PublicLibrary, if_none_match: IfNoneMatch = None
) -> Response:
    return _serve(AssetKind.AUDIO, asset_id, library, if_none_match)


@router.get("/sprites/{asset_id}")
def stream_sprite(
    asset_id: str, library: PublicLibrary, if_none_match: IfNoneMatch = None
) -> Response:
    return _serve(AssetKind.SPRITE, asset_id, library, if_none_match)


def _serve(
    kind: AssetKind, raw_id: str, library: PublicLibrary, if_none_match: str | None
) -> Response:
    # A malformed id gets the same answer as one that does not exist. Telling them apart only
    # tells a caller which ids are shaped right.
    asset_id = parse_id(raw_id)
    if asset_id is None or library is None:
        raise _not_found()
    asset = library.find(kind, asset_id)
    if asset is None:
        raise _not_found()

    headers = {
        "ETag": quote_tag(asset.sha256),
        "Cache-Control": IMMUTABLE,
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    if matches(if_none_match, asset.sha256):
        return Response(status_code=304, headers=headers)

    # The row is already in hand; open the bytes directly rather than look it up again.
    stream = library.blobs[kind].open(asset_id)
    if stream is None:
        # A row whose bytes are gone. A missing asset, not a server error.
        raise _not_found()

    allowed = AUDIO_TYPES if kind is AssetKind.AUDIO else IMAGE_TYPES
    if asset.content_type not in allowed:
        # Only reachable by a row written by something other than this service. Never serve
        # it under a type nobody checked.
        stream.close()
        raise _not_found()

    headers["Content-Length"] = str(asset.size_bytes)
    headers["Content-Disposition"] = _inline(asset.filename)
    return StreamingResponse(_chunks(stream), media_type=asset.content_type, headers=headers)


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    with stream:
        while chunk := stream.read(CHUNK):
            yield chunk


def _inline(filename: str) -> str:
    """An ASCII fallback for old clients, and RFC 6266's `filename*` for the real name: a
    header is latin-1, and a label like `thème.ogg` would otherwise break the response."""
    fallback = "".join(ch if " " <= ch <= "~" and ch not in '"\\' else "_" for ch in filename)
    return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")
