"""R1b: the schema, and the rules it keeps.

Half of these do not test code at all. They break a constraint on purpose and check the
database refuses, because a constraint nobody has seen fail is a constraint nobody knows is
there — and three of the rules below were application logic in the codebase this was extracted
from, where each was a bug at least once.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wavemaker.apps.content.adapters.postgres import PostgresWaveRepository
from wavemaker.platform.tenancy import TenancyError, ensure_project

NOW = datetime(2026, 9, 13, 16, 58, 40, tzinfo=UTC)

# Keys out of order and a float that a re-serialiser would rewrite as `2`. Both are here so
# that "the bytes come back unchanged" has something to be unchanged about.
DOCUMENT = '{"b":1,"a":2.0,"name":"First Steps"}'


def insert_wave(
    session: Session,
    project: uuid.UUID,
    wave_id: str,
    *,
    order: int,
    published: bool,
    document: str = DOCUMENT,
    name: str = "First Steps",
) -> None:
    session.execute(
        text("""
            insert into wave (project_id, wave_id, schema_uri, schema_version, name,
                              wave_order, published, config_json, created_at, updated_at)
            values (:p, :w, 'https://ludus/schema/wave/v1', 1, :n, :o, :pub, :doc, :t, :t)
        """),
        {
            "p": project,
            "w": wave_id,
            "n": name,
            "o": order,
            "pub": published,
            "doc": document,
            "t": NOW,
        },
    )


def insert_level(
    session: Session, project: uuid.UUID, name: str, wave_ids: list[str], *, active: bool
) -> uuid.UUID:
    level = uuid.uuid4()
    session.execute(
        text("""
            insert into wave_level (id, project_id, name, active, created_at, updated_at)
            values (:id, :p, :n, :a, :t, :t)
        """),
        {"id": level, "p": project, "n": name, "a": active, "t": NOW},
    )
    for position, wave_id in enumerate(wave_ids):
        session.execute(
            text("""
                insert into wave_level_wave (project_id, wave_level_id, wave_id, position)
                values (:p, :l, :w, :pos)
            """),
            {"p": project, "l": level, "w": wave_id, "pos": position},
        )
    return level


@pytest.fixture
def project(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        return ensure_project(session, "default", "Default")


# --- the column pair ---------------------------------------------------------------------


def test_the_stored_bytes_come_back_exactly_as_written(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_wave(session, project, "demo_first_steps", order=0, published=True)
        session.commit()
        stored = PostgresWaveRepository(session, project).published_document("demo_first_steps")

    assert stored == DOCUMENT.encode(), "the ETag is a hash of these bytes, so they cannot move"


def test_the_generated_column_reorders_keys_which_is_why_it_is_not_the_source(  # type: ignore[no-untyped-def]
    session_factory, project
) -> None:
    """The whole reason for two columns, demonstrated rather than asserted in a comment."""
    with session_factory() as session:
        insert_wave(session, project, "demo_first_steps", order=0, published=True)
        session.commit()
        text_column, json_column = session.execute(
            text("select config_json, config::text from wave")
        ).one()

    assert text_column == DOCUMENT
    assert json_column != DOCUMENT, "jsonb normalises; serving from it would move every ETag"


# --- rules the database keeps -------------------------------------------------------------


def test_two_waves_cannot_claim_the_same_order(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_wave(session, project, "first", order=3, published=True)
        session.commit()
        with pytest.raises(IntegrityError):
            insert_wave(session, project, "second", order=3, published=True)
            session.commit()


def test_only_one_level_can_be_active(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    """The rule the feature exists to guarantee.

    The Java could not enforce this in its schema: a partial unique index is PostgreSQL-only
    and its slice tests ran on H2, so it used a separate table instead. Here it is an index,
    and this test is what proves the index is really there.
    """
    with session_factory() as session:
        insert_level(session, project, "Act One", [], active=True)
        session.commit()
        with pytest.raises(IntegrityError):
            insert_level(session, project, "Act Two", [], active=True)
            session.commit()


def test_many_levels_may_be_inactive(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    """The other half: the index must not forbid what it was never meant to."""
    with session_factory() as session:
        insert_level(session, project, "Act One", [], active=False)
        insert_level(session, project, "Act Two", [], active=False)
        session.commit()
        count = session.execute(text("select count(*) from wave_level")).scalar_one()
    assert count == 2


def test_a_level_cannot_borrow_a_wave_from_another_project(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The composite foreign key. A row claiming a level from one project and a wave from
    another does not fail a check somewhere — it fails to be insertable."""
    with session_factory() as session:
        mine = ensure_project(session, "default", "Default")
        theirs = uuid.uuid4()
        session.execute(
            text("insert into project (id, slug, name, created_at) values (:i,'other','O',:t)"),
            {"i": theirs, "t": NOW},
        )
        insert_wave(session, theirs, "their_wave", order=0, published=True)
        level = insert_level(session, mine, "Act One", [], active=False)
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text("""
                    insert into wave_level_wave (project_id, wave_level_id, wave_id, position)
                    values (:p, :l, 'their_wave', 0)
                """),
                {"p": mine, "l": level},
            )
            session.commit()


def test_deleting_a_wave_removes_it_from_every_level(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    """In the database, rather than in whichever service method happened to remember."""
    with session_factory() as session:
        insert_wave(session, project, "doomed", order=0, published=True)
        insert_level(session, project, "Act One", ["doomed"], active=True)
        session.commit()

        session.execute(text("delete from wave where wave_id = 'doomed'"))
        session.commit()
        remaining = session.execute(text("select count(*) from wave_level_wave")).scalar_one()
    assert remaining == 0


# --- tenancy --------------------------------------------------------------------------------


def test_provisioning_the_project_twice_gives_the_same_project(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Startup runs this every time, so it has to be idempotent rather than merely first-run."""
    with session_factory() as session:
        first = ensure_project(session, "default", "Default")
        second = ensure_project(session, "default", "Default")
    assert first == second


def test_a_project_slug_that_is_not_a_slug_is_refused(session_factory) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session, pytest.raises(TenancyError):
        ensure_project(session, "Not A Slug", "Default")


# --- the repository, against real rows --------------------------------------------------------


def test_the_catalogue_is_published_waves_in_play_order(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_wave(session, project, "second", order=1, published=True, name="Crossfire")
        insert_wave(session, project, "first", order=0, published=True, name="First Steps")
        insert_wave(session, project, "draft", order=2, published=False, name="Pressure")
        session.commit()
        catalogue = PostgresWaveRepository(session, project).published_catalogue()

    assert [wave.id for wave in catalogue] == ["first", "second"]


def test_a_draft_is_absent_rather_than_hidden(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_wave(session, project, "draft", order=0, published=False)
        session.commit()
        repository = PostgresWaveRepository(session, project)

        assert repository.find_published("draft") is None
        assert repository.published_document("draft") is None


def test_a_batch_answers_in_the_order_it_was_asked(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_wave(session, project, "first", order=0, published=True)
        insert_wave(session, project, "second", order=1, published=True)
        insert_wave(session, project, "draft", order=2, published=False)
        session.commit()
        found = PostgresWaveRepository(session, project).published_documents(
            ["second", "draft", "first", "unknown"]
        )

    assert list(found) == ["second", "first"], "the client's order, not the database's"


def test_an_empty_batch_is_an_empty_answer(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        assert PostgresWaveRepository(session, project).published_documents([]) == {}


def test_the_active_level_keeps_its_waves_in_position_order(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_wave(session, project, "first", order=0, published=True)
        insert_wave(session, project, "second", order=1, published=True)
        insert_wave(session, project, "draft", order=2, published=False)
        insert_level(session, project, "Act One", ["first", "second", "draft"], active=True)
        insert_level(session, project, "Act Two", [], active=False)
        session.commit()
        level = PostgresWaveRepository(session, project).active_level()

    assert level is not None
    assert level.name == "Act One"
    # Drafts included here on purpose: which of them a client may see is decided when the
    # level is served. A level that dropped them could never say "2 of 3 reach players".
    assert level.wave_ids == ["first", "second", "draft"]


def test_no_active_level_is_nothing_rather_than_an_error(session_factory, project) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        insert_level(session, project, "Act One", [], active=False)
        session.commit()
        assert PostgresWaveRepository(session, project).active_level() is None
