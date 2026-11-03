"""The database connection, and running the migrations that shape it.

PostgreSQL only, and that is a decision rather than an omission. The content design rests on
two PostgreSQL features — a `jsonb` column generated from stored text, and a partial unique
index — and a second dialect that supports neither would mean either two hand-written schemas
or an invariant that is enforced in production and unprovable in tests.

The Java carried exactly that cost: its slice tests ran against H2, so the generated column and
the "one active level" rule had to live in a vendor directory, and the one rule the feature
existed to guarantee could not be proved by the tests that ran on every build. Tests here run
against a real PostgreSQL in a container instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from wavemaker.platform.kernel.storable import UnstorableText, unstorable

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def create_database_engine(url: str) -> Engine:
    """`pool_pre_ping` because a service outlives its connections.

    Without it the first request after a database restart, or after a connection has been idle
    long enough for a proxy to drop it, fails with a stale socket rather than quietly opening
    a new one.

    Every statement's parameters pass through `_refuse_unstorable_text` on the way out.
    """
    engine = create_engine(url, pool_pre_ping=True, future=True)
    event.listen(engine, "before_cursor_execute", _refuse_unstorable_text)
    return engine


def _refuse_unstorable_text(
    connection: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    """Refuse text PostgreSQL cannot hold before it is sent, whichever route sent it.

    A route that stores client text checks each field itself, so its refusal names the field.
    This is for the one that does not — a lookup by a path segment, or the next route somebody
    writes — so that it still answers the caller's 422 instead of the driver's 500. It raises
    `UnstorableText`, which the HTTP layer answers; nothing has reached the database yet.
    """
    pending: list[Any] = [parameters]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            reason = unstorable(value)
            if reason:
                raise UnstorableText(None, reason)
        elif isinstance(value, Mapping):
            pending.extend(value.values())
        elif isinstance(value, list | tuple):
            pending.extend(value)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def migrate(url: str) -> None:
    """Bring a database up to the current schema.

    Run at startup rather than by hand, so a deployment cannot serve requests against a schema
    it has not been migrated to — which is the failure where every read works and one write
    fails hours later.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
