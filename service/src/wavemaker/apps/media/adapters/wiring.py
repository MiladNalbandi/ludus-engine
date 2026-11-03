"""Putting a `MediaLibrary` together for one request, from what the service was started with.

Two things must be configured for media to work at all — a database for the rows and a blob
directory for the bytes. The admin side answers 503 naming whichever is missing; the public
side answers 404, because a fresh install with nothing configured should look like a service
with no art rather than a broken one, the same answer the content app gives with no database.

One session per request, closed when the request ends, as in the content app.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from wavemaker.apps.media.adapters.ffmpeg import FfmpegMixer
from wavemaker.apps.media.adapters.postgres import PostgresAssetCatalogue
from wavemaker.apps.media.adapters.settings import MediaSettings, media_settings
from wavemaker.apps.media.application.library import Limits, MediaLibrary
from wavemaker.apps.media.domain.asset import AssetKind
from wavemaker.platform.storage.blobs import FilesystemBlobs

# One namespace per kind, so audio and sprites cannot end up in each other's directory.
NAMESPACES = {AssetKind.AUDIO: "media-audio", AssetKind.SPRITE: "media-sprites"}

Configured = Annotated[MediaSettings, Depends(media_settings)]


def _missing(request: Request) -> str | None:
    if getattr(request.app.state, "session_factory", None) is None:
        return "This service has no database configured."
    if getattr(request.app.state, "blob_directory", None) is None:
        return (
            "This service stores no files: set WAVEMAKER_BLOB_DIRECTORY to a writable directory "
            "(under Docker, a volume) to turn media on."
        )
    return None


@contextmanager
def _opened(request: Request, settings: MediaSettings) -> Iterator[MediaLibrary]:
    state = request.app.state
    mixer = None
    if settings.ffmpeg_binary is not None:
        mixer = FfmpegMixer(
            settings.ffmpeg_binary,
            timeout=settings.mix_timeout_seconds,
            max_output_bytes=settings.mix_max_output_bytes,
            max_tracks=settings.mix_max_tracks,
        )
    with state.session_factory() as session:
        yield MediaLibrary(
            PostgresAssetCatalogue(session, state.project_id),
            {
                kind: FilesystemBlobs(state.blob_directory, namespace)
                for kind, namespace in NAMESPACES.items()
            },
            Limits(audio_bytes=settings.max_audio_bytes, sprite_bytes=settings.max_sprite_bytes),
            mixer,
        )


def admin_library(request: Request, settings: Configured) -> Iterator[MediaLibrary]:
    missing = _missing(request)
    if missing is not None:
        raise HTTPException(status_code=503, detail=missing)
    with _opened(request, settings) as library:
        yield library


def public_library(request: Request, settings: Configured) -> Iterator[MediaLibrary | None]:
    if _missing(request) is not None:
        yield None
        return
    with _opened(request, settings) as library:
        yield library


AdminLibrary = Annotated[MediaLibrary, Depends(admin_library)]
PublicLibrary = Annotated[MediaLibrary | None, Depends(public_library)]
