"""A real PostgreSQL for the tests that need one.

Not SQLite, and not a second dialect. Two things the content design rests on — a `jsonb`
column generated from stored text, and a partial unique index — exist only in PostgreSQL, and
a test run against something else would pass while proving nothing about what ships.

The container starts once per session. Each test that needs a clean schema gets one, which is
cheaper than a container per test and more honest than tests that depend on each other's rows.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Ryuk is testcontainers' cleanup sidecar; it bind-mounts the Docker socket, which this
# machine's Docker refuses ("operation not supported"). The containers here are started and
# stopped by a context manager that runs either way, so the sidecar has nothing to clean up.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from testcontainers.community.postgres import PostgresContainer

from wavemaker.platform.persistence.engine import (
    create_database_engine,
    create_session_factory,
    migrate,
)

IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(IMAGE, driver="psycopg") as container:
        yield container


@pytest.fixture
def database_url(postgres: PostgresContainer) -> Iterator[str]:
    """A migrated database with nothing in it.

    The schema is dropped and rebuilt per test rather than rows being deleted, because a test
    that leaks rows into the next one passes locally and fails on CI, on whichever ordering
    the runner happened to choose. That exact failure cost a day on the Java side.
    """
    url = postgres.get_connection_url()
    engine = create_database_engine(url)
    with engine.begin() as connection:
        from sqlalchemy import text

        connection.execute(text("drop schema public cascade; create schema public"))
    engine.dispose()

    migrate(url)
    yield url


@pytest.fixture
def session_factory(database_url: str):  # type: ignore[no-untyped-def]
    engine = create_database_engine(database_url)
    yield create_session_factory(engine)
    engine.dispose()
