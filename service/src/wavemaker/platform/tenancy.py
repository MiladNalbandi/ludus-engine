"""Which game's data this request is about.

A self-hosted install holds exactly one project for the life of the deployment, and every row
carries its id. That is not speculative: adding a tenant column to a finished schema later
means touching every table, foreign key, index, query and URL at once, and the cost of
carrying it from the first migration is one column.

The project is provisioned at startup rather than by a migration. A row created by a migration
records its existence in the migration history, and the two can come apart — a database
restored from a dump taken before the row, or a migration marked applied by hand. A check on
every start cannot come apart.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from wavemaker.platform.kernel.errors import PlatformError

SLUG = re.compile(r"^[a-z0-9_]+$")


class TenancyError(PlatformError):
    """The deployment's project could not be established."""


def ensure_project(session: Session, slug: str, name: str) -> uuid.UUID:
    """The id of this deployment's project, created on first start.

    Idempotent, and safe when two instances start at once: the insert is conditional and the
    unique index on slug settles any race, rather than a read-then-write that two processes
    can both pass.
    """
    if not SLUG.match(slug):
        raise TenancyError(
            f"'{slug}' is not a usable project slug. "
            "Use lower-case letters, digits and underscores."
        )

    session.execute(
        text("""
            insert into project (id, slug, name, created_at)
            values (:id, :slug, :name, :now)
            on conflict (slug) do nothing
        """),
        {"id": uuid.uuid4(), "slug": slug, "name": name, "now": datetime.now(UTC)},
    )
    session.commit()
    return current_project_id(session, slug)


def current_project_id(session: Session, slug: str) -> uuid.UUID:
    found = session.execute(
        text("select id from project where slug = :slug"), {"slug": slug}
    ).scalar_one_or_none()
    if found is None:
        raise TenancyError(
            f"No project '{slug}' exists. The service provisions it at startup, so this "
            "database has not been started against, or the row was removed."
        )
    return uuid.UUID(str(found))
