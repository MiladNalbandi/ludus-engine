"""Minting, listing, revoking and checking API keys.

An API key is a password that gets written into a config file, committed by accident, pasted
into a chat and shipped inside a game binary anybody can unpack. Every decision here follows
from assuming all of that happens to at least one key:

- it is shown once, when it is minted, and stored only as a sha256 digest;
- it can never be more than a viewer, by a CHECK in the schema rather than a default here;
- it buys exactly one thing, a player session, and touches no player's state itself;
- revoking it is a timestamp, so the record of when it stopped working survives the incident.

A digest rather than a password hash, unlike an account's password: the key is 256 random bits
this service generated, not something a person chose, so there is no dictionary to slow down.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from wavemaker.platform.identity.tokens import Role

# Makes a leaked key recognisable as one. Secret scanners match on patterns like this, which
# turns "somebody committed a key" from a silent event into an alert.
KEY_PREFIX = "wm_"

# How much of a key is shown in a list: the marker and eight random characters. Enough to tell
# two keys apart, nowhere near enough to guess either.
VISIBLE_LENGTH = len(KEY_PREFIX) + 8

MAX_NAME_LENGTH = 120

COLUMNS = "id, name, prefix, role, created_at, revoked_at"


@dataclass(frozen=True, slots=True)
class ApiKey:
    id: uuid.UUID
    name: str
    prefix: str
    role: Role
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class NewApiKey:
    """A key and the one and only copy of its secret."""

    key: ApiKey
    secret: str


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue(session: Session, project: uuid.UUID, name: str) -> NewApiKey:
    """Mint a key. The returned secret exists nowhere else, and cannot be recovered afterwards by
    anyone, including whoever runs the database."""
    secret = KEY_PREFIX + secrets.token_urlsafe(32)
    row = session.execute(
        text(f"""
            insert into api_key (id, project_id, name, prefix, secret_digest, role, created_at)
            values (:id, :project, :name, :prefix, :digest, :role, :now)
            returning {COLUMNS}
        """),
        {
            "id": uuid.uuid4(),
            "project": project,
            "name": name,
            "prefix": secret[:VISIBLE_LENGTH],
            "digest": digest(secret),
            "role": Role.VIEWER.value,
            "now": datetime.now(UTC),
        },
    ).one()
    session.commit()
    return NewApiKey(key=_key(row), secret=secret)


def list_keys(session: Session, project: uuid.UUID) -> list[ApiKey]:
    """Every key, revoked ones included, oldest first."""
    rows = session.execute(
        text(f"select {COLUMNS} from api_key where project_id = :project order by created_at, id"),
        {"project": project},
    ).all()
    return [_key(row) for row in rows]


def revoke(session: Session, project: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
    """Stamp a key revoked, or nothing when this project has no such key.

    Revoking twice keeps the first stamp. The moment a key stopped working is a fact, and a
    second click in an admin screen is not a reason to rewrite it.
    """
    row = session.execute(
        text(f"""
            update api_key set revoked_at = coalesce(revoked_at, :now)
            where project_id = :project and id = :id
            returning {COLUMNS}
        """),
        {"now": datetime.now(UTC), "project": project, "id": key_id},
    ).one_or_none()
    session.commit()
    return None if row is None else _key(row)


def authenticate(session: Session, project: uuid.UUID, presented: str) -> ApiKey | None:
    """The live key this secret is, or nothing — unknown and revoked look the same."""
    if not presented:
        return None
    row = session.execute(
        text(f"""
            select {COLUMNS} from api_key
            where project_id = :project and secret_digest = :digest and revoked_at is null
        """),
        {"project": project, "digest": digest(presented)},
    ).one_or_none()
    return None if row is None else _key(row)


def _key(row: Any) -> ApiKey:
    return ApiKey(
        id=uuid.UUID(str(row.id)),
        name=row.name,
        prefix=row.prefix,
        role=Role(row.role),
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )
