"""Reading and creating accounts.

Addresses are lower-cased here, on the way in, and the database refuses anything else. Folding
case in the query instead would let two rows exist for one mailbox and make which account you
get depend on which query ran.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from wavemaker.platform.identity.passwords import hash_password
from wavemaker.platform.identity.tokens import Role


@dataclass(frozen=True, slots=True)
class Account:
    id: uuid.UUID
    email: str
    password_hash: str
    role: Role
    enabled: bool


def normalise(email: str) -> str:
    return email.strip().lower()


def find_by_email(session: Session, project: uuid.UUID, email: str) -> Account | None:
    row = session.execute(
        text("""
            select id, email, password_hash, role, enabled from account
            where project_id = :project and email = :email
        """),
        {"project": project, "email": normalise(email)},
    ).one_or_none()
    if row is None:
        return None
    return Account(
        id=uuid.UUID(str(row.id)),
        email=row.email,
        password_hash=row.password_hash,
        role=Role(row.role),
        enabled=row.enabled,
    )


def ensure_account(
    session: Session, project: uuid.UUID, email: str, password: str, role: Role
) -> uuid.UUID:
    """Create this account if it is not there, and leave it alone if it is.

    Startup runs this every time, so it must not reset a password an administrator changed.
    `do nothing` rather than `do update` is the difference between provisioning an account and
    silently restoring whatever was in the environment at deploy time.
    """
    session.execute(
        text("""
            insert into account (id, project_id, email, password_hash, role, created_at)
            values (:id, :project, :email, :hash, :role, :now)
            on conflict (project_id, email) do nothing
        """),
        {
            "id": uuid.uuid4(),
            "project": project,
            "email": normalise(email),
            "hash": hash_password(password),
            "role": role.value,
            "now": datetime.now(UTC),
        },
    )
    session.commit()
    account = find_by_email(session, project, email)
    assert account is not None  # just inserted, or already there
    return account.id
