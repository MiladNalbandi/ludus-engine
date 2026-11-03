"""Players: who is playing, per project.

Part of the platform rather than of any app, because every player-facing app needs a player
and apps may not import each other. Economy, inventory and leaderboards all point at this
table; none of them owns it.

The service does not authenticate a player. It cannot: it holds no password for them, on
purpose. The game vouches for the identifier, and an API key says which game is vouching. A
game with no server of its own therefore gets device-level trust — honest, and said here
rather than implied to be more.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from wavemaker.platform.kernel.errors import PlatformError

MAX_EXTERNAL_ID_LENGTH = 190
MAX_DISPLAY_NAME_LENGTH = 120

COLUMNS = "id, external_id, display_name, created_at, last_seen_at"


class PlayerError(PlatformError):
    """A request about a player that cannot be acted on as it stands. `pointer` names the
    field, so a client can show the problem where it is."""

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer


@dataclass(frozen=True, slots=True)
class Player:
    id: uuid.UUID
    external_id: str
    display_name: str | None
    created_at: datetime
    last_seen_at: datetime


def external_id_of(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlayerError("/externalId", "a session needs the game's own identifier for the player")
    trimmed = value.strip()
    if len(trimmed) > MAX_EXTERNAL_ID_LENGTH:
        raise PlayerError(
            "/externalId", f"an identifier is at most {MAX_EXTERNAL_ID_LENGTH} characters"
        )
    return trimmed


def display_name_of(value: object) -> str | None:
    """A name the player chose, or None to clear it. Blank clears it, like the contract says."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlayerError("/displayName", "a display name is text")
    trimmed = value.strip()
    if len(trimmed) > MAX_DISPLAY_NAME_LENGTH:
        raise PlayerError(
            "/displayName", f"a display name is at most {MAX_DISPLAY_NAME_LENGTH} characters"
        )
    return trimmed or None


def start(session: Session, project: uuid.UUID, external_id: str) -> Player:
    """The player this identifier names, created on first sight, and seen now.

    One statement, an upsert on the unique (project, identifier). Find-then-insert has the same
    race the wallet's first grant had: two requests from a first launch both find nothing, both
    insert, and one of them fails — so a player's very first session is an error, on exactly
    the path where a client is least able to recover. Here the database settles it, and both
    requests get the same player.
    """
    now = datetime.now(UTC)
    row = session.execute(
        text(f"""
            insert into player (id, project_id, external_id, created_at, last_seen_at)
            values (:id, :project, :external_id, :now, :now)
            on conflict (project_id, external_id) do update
                set last_seen_at = greatest(player.last_seen_at, excluded.last_seen_at)
            returning {COLUMNS}
        """),
        {"id": uuid.uuid4(), "project": project, "external_id": external_id, "now": now},
    ).one()
    session.commit()
    return _player(row)


def find(session: Session, project: uuid.UUID, player: uuid.UUID) -> Player | None:
    row = session.execute(
        text(f"select {COLUMNS} from player where project_id = :project and id = :id"),
        {"project": project, "id": player},
    ).one_or_none()
    return None if row is None else _player(row)


def rename(
    session: Session, project: uuid.UUID, player: uuid.UUID, display_name: str | None
) -> Player | None:
    row = session.execute(
        text(f"""
            update player set display_name = :name
            where project_id = :project and id = :id
            returning {COLUMNS}
        """),
        {"name": display_name, "project": project, "id": player},
    ).one_or_none()
    session.commit()
    return None if row is None else _player(row)


def _player(row: Any) -> Player:
    return Player(
        id=uuid.UUID(str(row.id)),
        external_id=row.external_id,
        display_name=row.display_name,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    )
