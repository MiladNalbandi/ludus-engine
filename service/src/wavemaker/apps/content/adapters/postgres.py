"""Reading content out of PostgreSQL, behind the same port the in-memory one implements.

Every query filters on `project_id` and on `published`, and both filters live here rather than
in a route. "Which rows may a client see" is a storage question; a route that filtered them
itself is a route that can forget to, and the thing it forgets is unreleased content.

Documents come back out of `config_json`, never out of the generated `config` column. The text
column holds the bytes that were written; the jsonb column is derived from them and reorders
keys, so serving from it would change every client's ETag without any content changing.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from wavemaker.apps.content.domain.wave import PlayableLevel, WaveSummary

SUMMARY_COLUMNS = """
    wave_id, name, wave_order, schema_version, published, created_at, updated_at
"""


class PostgresWaveRepository:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def published_catalogue(self) -> Sequence[WaveSummary]:
        rows = self._session.execute(
            text(f"""
                select {SUMMARY_COLUMNS} from wave
                where project_id = :project and published
                order by wave_order
            """),
            {"project": self._project},
        ).all()
        return [_summary(row) for row in rows]

    def find_published(self, wave_id: str) -> WaveSummary | None:
        row = self._session.execute(
            text(f"""
                select {SUMMARY_COLUMNS} from wave
                where project_id = :project and wave_id = :wave and published
            """),
            {"project": self._project, "wave": wave_id},
        ).one_or_none()
        return None if row is None else _summary(row)

    def published_document(self, wave_id: str) -> bytes | None:
        found = self._session.execute(
            text("""
                select config_json from wave
                where project_id = :project and wave_id = :wave and published
            """),
            {"project": self._project, "wave": wave_id},
        ).scalar_one_or_none()
        return None if found is None else str(found).encode()

    def published_documents(self, wave_ids: Sequence[str]) -> Mapping[str, bytes]:
        if not wave_ids:
            # `in ()` is not valid SQL, and an empty batch is a legitimate question with an
            # empty answer rather than an error.
            return {}

        rows = self._session.execute(
            text("""
                select wave_id, config_json from wave
                where project_id = :project and published and wave_id = any(:waves)
            """),
            {"project": self._project, "waves": list(wave_ids)},
        ).all()
        # Keyed by the order asked for, so a client gets its own ordering back rather than the
        # database's. Ids that are drafts or unknown are simply absent.
        found = {row.wave_id: str(row.config_json).encode() for row in rows}
        return {wave_id: found[wave_id] for wave_id in wave_ids if wave_id in found}

    def active_level(self) -> PlayableLevel | None:
        level = self._session.execute(
            text("""
                select id, name from wave_level
                where project_id = :project and active
            """),
            {"project": self._project},
        ).one_or_none()
        if level is None:
            return None

        # Every wave the level names, drafts included. Which of them a client may see is
        # decided when the level is served — a level that dropped its drafts here could never
        # tell an editor "2 of 3 reach players".
        wave_ids = (
            self._session.execute(
                text("""
                select wave_id from wave_level_wave
                where wave_level_id = :level and project_id = :project
                order by position
            """),
                {"level": level.id, "project": self._project},
            )
            .scalars()
            .all()
        )

        return PlayableLevel(id=str(level.id), name=level.name, wave_ids=list(wave_ids))


def _summary(row: Any) -> WaveSummary:
    return WaveSummary(
        id=row.wave_id,
        name=row.name,
        order=row.wave_order,
        schema_version=row.schema_version,
        published=row.published,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
