"""A real PostgreSQL for the tests that need one.

Not SQLite, and not a second dialect. Two things the content design rests on — a `jsonb`
column generated from stored text, and a partial unique index — exist only in PostgreSQL, and
a test run against something else would pass while proving nothing about what ships.

The container starts once per session. Each test that needs a clean schema gets one, which is
cheaper than a container per test and more honest than tests that depend on each other's rows.
"""

from __future__ import annotations

import os
import uuid
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
def isolated_database_url(postgres: PostgresContainer) -> Iterator[str]:
    """A migrated database of its own, created for one test and dropped after it.

    For tests whose rows are committed by other threads, which nothing can roll back. The
    Java's wallet concurrency test shared its module's database, its committed rows collided
    with another test's, and it passed locally and failed on CI depending on ordering. A
    database nobody else connects to makes that isolation structural rather than a matter of
    who happens to run first.
    """
    from sqlalchemy import create_engine, make_url, text

    shared = postgres.get_connection_url()
    name = f"isolated_{uuid.uuid4().hex}"
    server = create_engine(shared, isolation_level="AUTOCOMMIT")
    with server.connect() as connection:
        connection.execute(text(f'create database "{name}"'))

    url = make_url(shared).set(database=name).render_as_string(hide_password=False)
    migrate(url)
    try:
        yield url
    finally:
        with server.connect() as connection:
            connection.execute(text(f'drop database if exists "{name}" with (force)'))
        server.dispose()


@pytest.fixture
def session_factory(database_url: str):  # type: ignore[no-untyped-def]
    engine = create_database_engine(database_url)
    yield create_session_factory(engine)
    engine.dispose()
