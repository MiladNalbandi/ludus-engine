"""The level store below the routes: what happens when the checks in front of the database
are missed, and when two authors replace one level at the same moment.

The routes check for missing and repeated waves before writing, so through the API the
constraints never fire. That is exactly why they are tested here, by going around the checks:
a check that runs first is a courtesy to the author, and the constraint is what is actually
relied on. When the two disagree — a wave deleted between the check and the insert — the
author must still get a 422, not a 500.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from wavemaker.apps.content.adapters import postgres
from wavemaker.apps.content.adapters.postgres import PostgresWaveRepository
from wavemaker.apps.content.domain.document import WaveDocument
from wavemaker.apps.content.domain.level import LevelDraft
from wavemaker.apps.content.domain.wave import LevelSummary, Rejected
from wavemaker.platform.persistence.engine import create_session_factory
from wavemaker.platform.tenancy import ensure_project

THREADS = 12
WAVES = [f"w{n}" for n in range(6)]


def a_wave(wave_id: str, order: int) -> WaveDocument:
    return WaveDocument.read(
        json.dumps(
            {"id": wave_id, "name": wave_id, "progression_config": {"order": order}}
        ).encode()
    )


@pytest.fixture
def project(session_factory: sessionmaker[Session]) -> uuid.UUID:
    with session_factory() as session:
        project_id = ensure_project(session, "levels", "Levels")
        store = PostgresWaveRepository(session, project_id)
        for order, wave_id in enumerate(WAVES):
            store.save(a_wave(wave_id, order))
        return project_id


def store_for(session: Session, project: uuid.UUID) -> PostgresWaveRepository:
    return PostgresWaveRepository(session, project)


def a_level(session_factory: sessionmaker[Session], project: uuid.UUID) -> LevelSummary:
    with session_factory() as session:
        return store_for(session, project).create_level(LevelDraft("Act One", None, ("w0", "w1")))


# --- AC-2: the constraints answer, when the checks in front of them are gone -------------------


@pytest.mark.ac("AC-2")
def test_a_repeated_wave_that_reaches_the_database_is_a_rejection(
    session_factory: sessionmaker[Session], project: uuid.UUID
) -> None:
    """A draft built directly, so the domain's duplicate check never ran. The primary key on
    (level, wave) refuses it, and that must come back as something an author can read."""
    with session_factory() as session:
        store = store_for(session, project)
        with pytest.raises(Rejected, match="/waves"):
            store.create_level(LevelDraft("Act One", None, ("w0", "w1", "w0")))
        assert store.all_levels() == [], "the level row went with the rejected members"


@pytest.mark.ac("AC-2")
def test_a_shared_position_is_recognised_as_a_rejection(
    session_factory: sessionmaker[Session], project: uuid.UUID
) -> None:
    """Through the store a position is a list index, so two waves can share one only if two
    replacements interleave. Here the real violation is produced by hand, and the translator
    the store uses must recognise it by its constraint, not by luck in its message."""
    level = a_level(session_factory, project)
    with session_factory() as session:
        with pytest.raises(IntegrityError) as clash:
            session.execute(
                text("""
                    insert into wave_level_wave (project_id, wave_level_id, wave_id, position)
                    values (:p, :l, 'w2', 0)
                """),
                {"p": project, "l": uuid.UUID(level.id)},
            )
        session.rollback()

    rejection = postgres.membership_rejection(clash.value)
    assert rejection is not None
    assert "position" in str(rejection)


@pytest.mark.ac("AC-2")
def test_an_unrelated_violation_is_not_disguised_as_a_rejection(
    session_factory: sessionmaker[Session], project: uuid.UUID
) -> None:
    with session_factory() as session:
        with pytest.raises(IntegrityError) as clash:
            session.execute(
                text("""
                    insert into project (id, slug, name, created_at)
                    values (:i, 'levels', 'x', now())
                """),
                {"i": uuid.uuid4()},
            )
        session.rollback()
    assert postgres.membership_rejection(clash.value) is None


# --- AC-3: the composite foreign key, when the existence check is missed ------------------------


def missed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The existence check finds nothing wrong the first time it is asked, as it would if the
    wave were deleted between the check and the insert, and answers truthfully after that."""
    real = PostgresWaveRepository._missing_waves
    asked: list[int] = []

    def missed(self: PostgresWaveRepository, wave_ids: Sequence[str]) -> list[tuple[int, str]]:
        asked.append(1)
        return [] if len(asked) == 1 else real(self, wave_ids)

    monkeypatch.setattr(PostgresWaveRepository, "_missing_waves", missed)


@pytest.mark.ac("AC-3")
def test_a_wave_that_vanished_after_the_check_is_still_a_422(
    session_factory: sessionmaker[Session], project: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The race the check cannot close on its own: the check passes, then the insert meets a
    wave that is not there. The composite foreign key refuses it; the store must say which."""
    missed_once(monkeypatch)

    with session_factory() as session:
        store = store_for(session, project)
        with pytest.raises(Rejected) as refused:
            store.create_level(LevelDraft("Act One", None, ("w0", "ghost")))
        assert "ghost" in str(refused.value)
        assert store.all_levels() == []


@pytest.mark.ac("AC-3")
def test_a_wave_of_another_project_cannot_be_stored_even_past_the_check(
    session_factory: sessionmaker[Session], project: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_factory() as session:
        elsewhere = ensure_project(session, "elsewhere", "Elsewhere")
        store_for(session, elsewhere).save(a_wave("foreign", 0))

    missed_once(monkeypatch)
    with session_factory() as session, pytest.raises(Rejected, match="foreign"):
        store_for(session, project).create_level(LevelDraft("Act One", None, ("foreign",)))


# --- AC-4: concurrent replacements -------------------------------------------------------------


@pytest.fixture
def engine(isolated_database_url: str) -> Iterator[Engine]:
    """One connection per thread, so the replacements really do overlap."""
    created = create_engine(isolated_database_url, pool_size=THREADS, max_overflow=0)
    yield created
    created.dispose()


def replacement(n: int) -> tuple[str, ...]:
    """A different ordering, and a different length, for every thread."""
    rotated = WAVES[n % len(WAVES) :] + WAVES[: n % len(WAVES)]
    return tuple(rotated[: 2 + n % (len(WAVES) - 1)])


@pytest.mark.ac("AC-4")
def test_concurrent_replacements_of_one_level_each_land_whole(engine: Engine) -> None:
    """Twelve authors replace the same level at once. Every one is answered, none with an
    error, and the level ends as exactly one of their lists — not a blend of two, and not a
    position held twice. Deleting and re-inserting members without first taking the level's
    row makes the second writer's delete miss the first writer's rows, and the inserts then
    collide on the position."""
    factory = create_session_factory(engine)
    with factory() as session:
        project = ensure_project(session, "concurrent", "Concurrent")
        store = store_for(session, project)
        for order, wave_id in enumerate(WAVES):
            store.save(a_wave(wave_id, order))
        level = store.create_level(LevelDraft("Act One", None, tuple(WAVES)))

    gate = threading.Barrier(THREADS)

    def one(n: int) -> LevelSummary | Exception | None:
        with factory() as session:
            session.connection()
            gate.wait()
            try:
                return store_for(session, project).update_level(
                    level.id, LevelDraft(f"Take {n}", None, replacement(n))
                )
            except Exception as failed:
                return failed

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results: Sequence[LevelSummary | Exception | None] = list(pool.map(one, range(THREADS)))

    failures = [result for result in results if not isinstance(result, LevelSummary)]
    assert failures == [], "every replacement is answered with the level it wrote"

    with factory() as session:
        final = store_for(session, project).level(level.id)
        rows = session.execute(
            text("select count(*), count(distinct position) from wave_level_wave")
        ).one()
    assert final is not None
    ending = tuple(member.wave_id for member in final.waves)
    assert ending == replacement(int(final.name.removeprefix("Take "))), (
        "the name and the waves come from the same replacement"
    )
    assert rows[0] == rows[1] == len(ending), "one wave per position, and nothing left over"
