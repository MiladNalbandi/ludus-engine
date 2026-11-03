"""The public read surface, shaped by the contract frozen at v1.0.0.

Bodies are built by hand rather than from a response model on purpose. A stored document is
served as the exact bytes that were written, and the summary fields are spelled the way the
frozen document spells them. Both are wire details, and a serialiser that is free to reorder
or reformat is free to expire every client's cache without changing any content.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response

from wavemaker.apps.content.adapters.memory import InMemoryWaveRepository
from wavemaker.apps.content.adapters.postgres import PostgresWaveRepository
from wavemaker.apps.content.application.ports import WaveRepository
from wavemaker.apps.content.domain import app_config, hashing
from wavemaker.apps.content.domain.etag import matches, quote
from wavemaker.apps.content.domain.wave import WaveSummary
from wavemaker.platform.kernel.storable import storable

router = APIRouter(prefix="/api/v1/public", tags=["content"])

IfNoneMatch = Annotated[str | None, Header(alias="If-None-Match")]


def get_wave_repository(request: Request) -> Iterator[WaveRepository]:
    """Where content is read from: PostgreSQL when one is configured, nothing when not.

    A service with no database answers honestly — an empty catalogue with a stable hash —
    rather than failing at the first request. That is the shape a fresh install has before
    anyone has pointed it at a database, and it should look like a service with no content
    rather than a broken one.

    One session per request, closed when the request ends. A session held open across requests
    keeps a transaction open with it, and a long-lived read transaction is how a reader starts
    serving a snapshot of the world from an hour ago.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        yield InMemoryWaveRepository(waves=[], documents={}, level=None)
        return

    with factory() as session:
        yield PostgresWaveRepository(session, request.app.state.project_id)


Repository = Annotated[WaveRepository, Depends(get_wave_repository)]


def _moment(value: datetime) -> str:
    """`...Z`, the way the frozen contract writes a date-time. `+00:00` is the same instant
    and a different string, and some generated clients only parse the one they were given."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _summary(wave: WaveSummary) -> dict[str, Any]:
    return {
        "id": wave.id,
        "name": wave.name,
        "order": wave.order,
        "schemaVersion": wave.schema_version,
        "published": wave.published,
        "createdAt": _moment(wave.created_at),
        "updatedAt": _moment(wave.updated_at),
    }


def _conditional(body: Any, tag: str, if_none_match: str | None) -> Response:
    """One place where a tag is compared, so no route can forget to."""
    if matches(if_none_match, tag):
        return Response(status_code=304, headers={"ETag": quote(tag)})
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers={"ETag": quote(tag)},
    )


@router.get("/status")
def content_status(repository: Repository) -> Response:
    """The hash a client polls on every launch.

    `no-store`, because a cached answer to "has anything changed?" is an answer that cannot
    change, which makes the whole poll pointless.
    """
    body = {"contentHash": hashing.of_catalogue(repository.published_catalogue())}
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/waves")
def list_published_waves(repository: Repository, if_none_match: IfNoneMatch = None) -> Response:
    catalogue = repository.published_catalogue()
    # The same function that answers /status. Not a second one that ought to agree with it.
    return _conditional(
        [_summary(wave) for wave in catalogue], hashing.of_catalogue(catalogue), if_none_match
    )


@router.get("/waves/{wave_id}")
def get_published_wave(
    wave_id: str, repository: Repository, if_none_match: IfNoneMatch = None
) -> Response:
    wave = repository.find_published(wave_id)
    if wave is None:
        return _not_found()
    return _conditional(_summary(wave), hashing.of_catalogue([wave]), if_none_match)


@router.get("/waves/{wave_id}/raw")
def get_published_wave_document(
    wave_id: str, repository: Repository, if_none_match: IfNoneMatch = None
) -> Response:
    document = repository.published_document(wave_id)
    if document is None:
        return _not_found()

    tag = hashing.of_document(document)
    if matches(if_none_match, tag):
        return Response(status_code=304, headers={"ETag": quote(tag)})
    # The stored bytes, untouched. Parsing and re-dumping here would move the tag.
    return Response(content=document, media_type="application/json", headers={"ETag": quote(tag)})


@router.post("/waves/batch")
def batch_get_published_waves(request: dict[str, Any], repository: Repository) -> Response:
    ids = [
        storable(f"/ids/{index}", str(wave_id))
        for index, wave_id in enumerate(request.get("ids", []))
    ]
    found = repository.published_documents(ids)
    return Response(content=_as_object(found), media_type="application/json")


def _as_object(documents: Mapping[str, bytes]) -> bytes:
    """Join stored documents into one JSON object without reparsing any of them.

    A draft or an unknown id is simply absent. A client asking for ten waves and getting
    eight has the eight it may see, which is the same answer it would get one at a time.
    """
    parts = [
        json.dumps(wave_id).encode() + b":" + document for wave_id, document in documents.items()
    ]
    return b"{" + b",".join(parts) + b"}"


@router.get("/wave-levels/active")
def get_active_wave_level(repository: Repository, if_none_match: IfNoneMatch = None) -> Response:
    level = repository.active_level()
    if level is None:
        return _not_found()

    playable = _published_in(level.wave_ids, repository)
    body = {"id": level.id, "name": level.name, "waves": [_summary(w) for w in playable]}
    return _conditional(body, hashing.of_catalogue(playable), if_none_match)


@router.get("/app-config", operation_id="getPublicAppConfig")
def get_public_app_config(repository: Repository, if_none_match: IfNoneMatch = None) -> Response:
    """The settings this game should launch with: the stored bytes, tagged by a hash of them.

    Always an answer, `{}` for a project nobody configured. Fetched by every client on every
    launch, which is why the tag is over the exact bytes and nothing else.
    """
    document = repository.app_config() or app_config.EMPTY
    tag = hashing.of_document(document)
    if matches(if_none_match, tag):
        return Response(status_code=304, headers={"ETag": quote(tag)})
    return Response(content=document, media_type="application/json", headers={"ETag": quote(tag)})


def _published_in(wave_ids: Sequence[str], repository: Repository) -> list[WaveSummary]:
    """A level keeps its drafts; a client is served only the published ones, in level order."""
    found = (repository.find_published(wave_id) for wave_id in wave_ids)
    return [wave for wave in found if wave is not None]


def _not_found() -> Response:
    """404, never 403. A client that can tell "hidden" from "absent" has been told about
    unreleased content, which is the one thing publication exists to control."""
    return Response(
        content=json.dumps({"detail": "Not Found"}), status_code=404, media_type="application/json"
    )
