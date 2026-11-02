"""The authoring surface: what the editor talks to.

Every route here is behind a role. The public routes next door are anonymous by design; these
decide what those routes serve, so an unauthenticated write here would be an unauthenticated
change to what every player receives.

A document arrives as raw bytes and is stored as raw bytes. It is parsed twice on the way in —
once to validate it against the project's schema, once to read the handful of indexed fields —
and the parsed form is then thrown away. Storing it would mean re-serialising, and
re-serialising rewrites `2.0` as `2` and reorders keys, which moves every client's ETag on a
save that changed nothing.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from wavemaker.apps.content.adapters import schema
from wavemaker.apps.content.adapters.postgres import PostgresWaveRepository
from wavemaker.apps.content.application.ports import WaveStore
from wavemaker.apps.content.domain.bulk import BulkError, split_documents
from wavemaker.apps.content.domain.document import DocumentError, OrderTaken, WaveDocument
from wavemaker.apps.content.domain.wave import LevelSummary, WaveSummary
from wavemaker.platform.identity.http import requires
from wavemaker.platform.identity.tokens import Role

router = APIRouter(prefix="/api/v1/admin", tags=["authoring"])

# Viewers may look at drafts; only editors and administrators may change them.
READER = Depends(requires(Role.VIEWER, Role.EDITOR, Role.ADMIN))
WRITER = Depends(requires(Role.EDITOR, Role.ADMIN))


def get_wave_store(request: Request) -> Iterator[WaveStore]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        # Authoring with nowhere to author to. 503 rather than an empty list, which would
        # look to an editor like a project with no content.
        raise HTTPException(status_code=503, detail="This service has no database configured.")
    with factory() as session:
        yield PostgresWaveRepository(session, request.app.state.project_id)


Store = Annotated[WaveStore, Depends(get_wave_store)]


def _moment(value: datetime) -> str:
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


def _level(level: LevelSummary) -> dict[str, Any]:
    return {
        "id": level.id,
        "name": level.name,
        "description": level.description,
        "active": level.active,
        "waves": [
            {"waveId": member.wave_id, "published": member.published} for member in level.waves
        ],
        "createdAt": _moment(level.created_at),
        "updatedAt": _moment(level.updated_at),
    }


async def _accepted(request: Request) -> WaveDocument:
    """The request body, validated, with the indexed fields read out of it.

    Validation first, then the fields: a document that does not match the schema has no
    meaningful `name` or `order` to complain about, and reporting the second problem when the
    first is "this is not a wave" sends an author looking in the wrong place.
    """
    raw = await request.body()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as broken:
        raise HTTPException(status_code=400, detail=f"This is not JSON: {broken}") from broken

    try:
        schema.check(parsed)
        return WaveDocument.read(raw)
    except DocumentError as invalid:
        # 422: the request was understood and is not acceptable. A 400 would say it could not
        # be read, which is a different thing an author would debug differently.
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid


@router.get("/waves", dependencies=[READER])
def list_waves(store: Store) -> list[dict[str, Any]]:
    """Every wave, drafts included. This is the authoring view, not the client's."""
    return [_summary(wave) for wave in store.all_summaries()]


@router.get("/waves/next-order", dependencies=[READER])
def next_order(store: Store) -> dict[str, int]:
    """So an author is not asked to guess a free position and collide with somebody else."""
    return {"order": store.next_order()}


@router.post("/waves", dependencies=[WRITER], status_code=201)
async def create_wave(request: Request, store: Store) -> dict[str, Any]:
    document = await _accepted(request)
    if store.document(document.id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A wave called '{document.id}' already exists. Use PUT to replace it.",
        )
    return _saved(store, document)


@router.post("/waves/bulk", dependencies=[WRITER])
async def import_waves(request: Request, store: Store) -> list[dict[str, Any]]:
    """An all-or-nothing import of many documents.

    The array is split rather than parsed, so each document is stored as the bytes it was
    written with. Parsing the array and re-serialising its elements would rewrite `2.0` as `2`
    and reorder keys, moving the ETag of every wave in the batch.

    A problem names the document by position — `/2/name` means the third one — because that is
    the only way an author can find it in a file of thirty.
    """
    try:
        bodies = split_documents(await request.body())
    except BulkError as malformed:
        raise HTTPException(status_code=400, detail=str(malformed)) from malformed

    documents = []
    for index, body in enumerate(bodies):
        try:
            schema.check(json.loads(body))
            documents.append(WaveDocument.read(body))
        except json.JSONDecodeError as broken:
            raise HTTPException(status_code=400, detail=f"/{index}: {broken}") from broken
        except DocumentError as invalid:
            raise HTTPException(status_code=422, detail=f"/{index}{invalid}") from invalid

    try:
        return [_summary(wave) for wave in store.save_all(documents)]
    except OrderTaken as taken:
        raise HTTPException(status_code=422, detail=str(taken)) from taken


@router.get("/waves/{wave_id}", dependencies=[READER])
def get_wave_document(wave_id: str, store: Store) -> Response:
    document = store.document(wave_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No such wave.")
    # The stored bytes, as always. An author opening a wave and saving it unchanged must not
    # change its ETag.
    return Response(content=document, media_type="application/json")


@router.put("/waves/{wave_id}", dependencies=[WRITER])
async def replace_wave(wave_id: str, request: Request, store: Store) -> dict[str, Any]:
    document = await _accepted(request)
    if document.id != wave_id:
        # Two sources for one identity. Refusing is the only answer that cannot silently
        # rename a wave or overwrite a different one.
        raise HTTPException(
            status_code=422,
            detail=f"The document calls itself '{document.id}' but the path says '{wave_id}'.",
        )
    return _saved(store, document)


def _saved(store: WaveStore, document: WaveDocument) -> dict[str, Any]:
    try:
        return _summary(store.save(document))
    except OrderTaken as taken:
        raise HTTPException(status_code=422, detail=str(taken)) from taken


@router.delete("/waves/{wave_id}", dependencies=[WRITER], status_code=204)
def delete_wave(wave_id: str, store: Store) -> Response:
    if not store.delete(wave_id):
        raise HTTPException(status_code=404, detail="No such wave.")
    return Response(status_code=204)


@router.post("/waves/{wave_id}/publish", dependencies=[WRITER])
def publish_wave(wave_id: str, store: Store) -> dict[str, Any]:
    return _published(store, wave_id, True)


@router.post("/waves/{wave_id}/unpublish", dependencies=[WRITER])
def unpublish_wave(wave_id: str, store: Store) -> dict[str, Any]:
    return _published(store, wave_id, False)


def _published(store: WaveStore, wave_id: str, published: bool) -> dict[str, Any]:
    changed = store.set_published(wave_id, published)
    if changed is None:
        raise HTTPException(status_code=404, detail="No such wave.")
    return _summary(changed)


@router.get("/wave-levels", dependencies=[READER])
def list_wave_levels(store: Store) -> list[dict[str, Any]]:
    return [_level(level) for level in store.all_levels()]


@router.post("/wave-levels/{level_id}/activate", dependencies=[WRITER])
def activate_wave_level(level_id: str, store: Store) -> dict[str, Any]:
    activated = store.activate_level(level_id)
    if activated is None:
        raise HTTPException(status_code=404, detail="No such level.")
    return _level(activated)
