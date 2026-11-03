"""AC-8: twenty concurrent grants of one coin end at twenty.

The test the issue exists for. The Java's version of it reported eighteen. The statement was
fine; the bug was one layer up, on a player's *first* grant: several threads found no row, all
tried to insert, one won, and the losers were told "refused". Nothing failed. The player was two
coins short, and the only way to notice was to count on purpose.

Real threads, each with its own connection, against a real PostgreSQL. Their rows are committed,
since a worker cannot see a player in a transaction that has not been, so nothing can roll them
back — which is why this runs in a database of its own, created for each test and dropped after
it. The Java's shared one, leaked into the rest of the suite, and failed on CI only.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.community.postgres import PostgresContainer

from wavemaker.apps.economy.adapters.postgres import PostgresWallets
from wavemaker.apps.economy.domain.wallet import Balance, NotEnough
from wavemaker.platform.identity import players
from wavemaker.platform.persistence.engine import create_session_factory
from wavemaker.platform.tenancy import ensure_project

THREADS = 20
ROUNDS = 5

@pytest.fixture
def engine(isolated_database_url: str) -> Iterator[Engine]:
    """One connection per thread, so no worker waits on the pool and they really do collide."""
    from sqlalchemy import create_engine

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


def a_player(factory: sessionmaker[Session], project: uuid.UUID) -> uuid.UUID:
    with factory() as session:
        return players.start(session, project, f"device-{uuid.uuid4()}").id


def all_at_once[T](
    factory: sessionmaker[Session], project: uuid.UUID, work: Callable[[PostgresWallets], T]
) -> list[T | Exception]:
    """Run `work` on THREADS threads, released together once every one holds a connection."""
    gate = threading.Barrier(THREADS)

    def one(_: int) -> T | Exception:
        with factory() as session:
            session.connection()  # check out the connection before the gate, not after it
            gate.wait()
            try:
                return work(PostgresWallets(session, project))
            except Exception as failed:
                return failed

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(one, range(THREADS)))


def balance_of(factory: sessionmaker[Session], project: uuid.UUID, player: uuid.UUID) -> int:
    with factory() as session:
        balances = PostgresWallets(session, project).balances(player)
    return next((b.amount for b in balances if b.currency == "coins"), 0)


def test_ac8_the_concurrency_test_has_a_database_of_its_own(
    isolated_database_url: str, postgres: PostgresContainer
) -> None:
    assert isolated_database_url != postgres.get_connection_url()


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_ac8_twenty_concurrent_first_grants_of_one_coin_make_twenty(
    factory: sessionmaker[Session], project: uuid.UUID, round_number: int
) -> None:
    """A player with no wallet row at all, so every thread races to create it."""
    player = a_player(factory, project)

    results = all_at_once(factory, project, lambda wallets: wallets.grant(player, "coins", 1))

    refused = [result for result in results if isinstance(result, Exception)]
    assert refused == [], "no grant may be told it was refused"
    assert balance_of(factory, project, player) == THREADS

    # Each grant saw its own increment: the balances they report are 1..20, each exactly once.
    # Two grants reporting the same number would mean two of them read the same starting point.
    reported = sorted(result.amount for result in results if isinstance(result, Balance))
    assert reported == list(range(1, THREADS + 1))


def test_ac8_twenty_concurrent_spends_of_one_from_ten_let_exactly_ten_through(
    factory: sessionmaker[Session], project: uuid.UUID
) -> None:
    """A check-then-act lets more through, because the gap between reading the balance and
    writing it is exactly where another spend fits — and the result is a negative balance the
    schema was supposed to make impossible."""
    player = a_player(factory, project)
    with factory() as session:
        PostgresWallets(session, project).grant(player, "coins", 10)

    results = all_at_once(factory, project, lambda wallets: wallets.spend(player, "coins", 1))

    spent = [result for result in results if isinstance(result, Balance)]
    refused = [result for result in results if isinstance(result, NotEnough)]
    unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, NotEnough)]
    assert unexpected == [], "an overdraft is a refusal, never an error"
    assert len(spent) == 10
    assert len(refused) == 10
    assert sorted(result.amount for result in spent) == list(range(10))
    assert balance_of(factory, project, player) == 0
