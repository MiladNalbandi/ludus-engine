"""Asset metadata in PostgreSQL. Never asset bytes.

Every query filters on `project_id`, here rather than in a route: "which rows belong to this
project" is a storage question, and a route that filtered them itself is a route that can
forget to.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.orm import Session

from wavemaker.apps.media.domain.asset import Asset, AssetKind

# Table names come from this fixed mapping and never from a request, which is the only reason
# it is safe to put them into SQL with an f-string.
TABLES = {AssetKind.AUDIO: "audio_clip", AssetKind.SPRITE: "sprite"}
COLUMNS = "id, filename, content_type, size_bytes, content_sha256, created_at"


class PostgresAssetCatalogue:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def add(self, asset: Asset) -> None:
        self._session.execute(
            text(f"""
                insert into {TABLES[asset.kind]}
                    (id, project_id, filename, content_type, size_bytes, content_sha256, created_at)
                values (:id, :p, :name, :type, :size, :sha, :at)
            """),
            {
                "id": asset.id,
                "p": self._project,
                "name": asset.filename,
                "type": asset.content_type,
                "size": asset.size_bytes,
                "sha": asset.sha256,
                "at": asset.created_at,
            },
        )
        self._session.commit()

    def list(self, kind: AssetKind) -> Sequence[Asset]:
        rows = self._session.execute(
            text(f"""
                select {COLUMNS} from {TABLES[kind]}
                where project_id = :p
                order by created_at desc, id
            """),
            {"p": self._project},
        ).all()
        return [_asset(kind, row) for row in rows]

    def find(self, kind: AssetKind, asset_id: uuid.UUID) -> Asset | None:
        row = self._session.execute(
            text(f"select {COLUMNS} from {TABLES[kind]} where project_id = :p and id = :id"),
            {"p": self._project, "id": asset_id},
        ).one_or_none()
        return None if row is None else _asset(kind, row)

    def remove(self, kind: AssetKind, asset_id: uuid.UUID) -> bool:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                text(f"delete from {TABLES[kind]} where project_id = :p and id = :id"),
                {"p": self._project, "id": asset_id},
            ),
        )
        self._session.commit()
        return bool(result.rowcount)


def _asset(kind: AssetKind, row: Any) -> Asset:
    return Asset(
        id=row.id,
        kind=kind,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        sha256=row.content_sha256,
        created_at=row.created_at,
    )
