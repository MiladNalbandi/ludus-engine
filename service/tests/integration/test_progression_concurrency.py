"""R6 AC-6 and AC-8 under concurrency: no award is lost, and two saves of the curve are not a 500.

Real threads, each with its own connection, in a database of the test's own, for the wallet
test's reason: their rows are committed and nothing can roll them back.
"""

from __future__ import annotations

import importlib
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from wavemaker.apps.economy.adapters.postgres import PostgresWallets
from wavemaker.apps.progression.adapters.postgres import PostgresProgression
from wavemaker.apps.progression.domain.curve import Grant, Stage
from wavemaker.platform import currency
from wavemaker.platform.identity import players
from wavemaker.platform.persistence.engine import create_session_factory
from wavemaker.platform.tenancy import ensure_project

THREADS = 20
ROUNDS = 3


@pytest.fixture
def engine(isolated_database_url: str) -> Iterator[Engine]:
    created = create_engine(isolated_database_url, pool_size=THREADS, max_overflow=0)
    yield created
    created.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def project(factory: sessionmaker[Session]) -> uuid.UUID:
    with factory() as session:
        return ensure_project(session, "concurrency", "Concurrency")


def all_at_once[T](
    factory: sessionmaker[Session],
    project: uuid.UUID,
    work: Callable[[int, PostgresProgression], T],
) -> list[T | Exception]:
    gate = threading.Barrier(THREADS)

    def one(index: int) -> T | Exception:
        with factory() as session:
            session.connection()
            gate.wait()
            try:
                return work(index, PostgresProgression(session, project))
            except Exception as failed:
                return failed

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(one, range(THREADS)))


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_ac8_twenty_concurrent_first_awards_of_one_xp_make_twenty(
    factory: sessionmaker[Session], project: uuid.UUID, round_number: int
) -> None:
    """A player with no XP row, so every thread races to create it."""
    with factory() as session:
        player = players.start(session, project, f"device-{uuid.uuid4()}").id

    results = all_at_once(
        factory, project, lambda _, progression: progression.reward(player, 1, [], None)
    )

    assert [r for r in results if isinstance(r, Exception)] == []
    reported = sorted(r[1] for r in results if not isinstance(r, Exception))
    assert reported == list(range(1, THREADS + 1)), "each award saw its own increment"
    with factory() as session:
        assert PostgresProgression(session, project).xp(player) == THREADS


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_ac6_concurrent_replacements_of_the_curve_all_succeed_and_one_wins_whole(
    factory: sessionmaker[Session], project: uuid.UUID, round_number: int
) -> None:
    """Delete-then-insert does not serialise by itself under read committed: the second delete
    cannot see the first's new rows, and its insert collides with them. Without the lock, most
    of these came back as unique violations — a 500 for two editors pressing save together."""

    def curve(index: int) -> list[Stage]:
        return [Stage(stage, stage * (index + 1) * 10, f"v{index}") for stage in range(1, 6)]

    results = all_at_once(
        factory, project, lambda index, progression: progression.replace_curve(curve(index))
    )

    assert [r for r in results if isinstance(r, Exception)] == []
    with factory() as session:
        final = PostgresProgression(session, project).curve()
    assert final in [curve(index) for index in range(THREADS)], "one whole curve, not a blend"


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_ac8_twenty_concurrent_rewards_with_coins_lose_neither_coins_nor_xp(
    factory: sessionmaker[Session], project: uuid.UUID, round_number: int
) -> None:
    """Through the ledger the economy provides, as the service uses it. The player has neither
    an XP row nor a balance, so every thread races to create both, in one transaction each."""
    importlib.import_module("wavemaker.apps.economy")
    ledger = currency.provided()
    assert ledger is not None, "loading the economy app provides no currency ledger"
    with factory() as session:
        player = players.start(session, project, f"device-{uuid.uuid4()}").id

    results = all_at_once(
        factory,
        project,
        lambda _, progression: progression.reward(player, 1, [Grant("coins", 1)], ledger),
    )

    assert [r for r in results if isinstance(r, Exception)] == []
    rewarded = [r for r in results if not isinstance(r, Exception)]
    assert sorted(r[1] for r in rewarded) == list(range(1, THREADS + 1))
    coins = sorted(balance.amount for balances, _ in rewarded for balance in balances)
    assert coins == list(range(1, THREADS + 1)), "each reward saw its own coin"
    with factory() as session:
        assert PostgresProgression(session, project).xp(player) == THREADS
        assert [b.amount for b in PostgresWallets(session, project).balances(player)] == [THREADS]
