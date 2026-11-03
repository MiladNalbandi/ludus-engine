"""R6 AC-4: a walk through a board returns each unchanged row exactly once while scores are
being written.

The criterion R6 is done by, and stated no wider than it is true. A row whose score does not
change appears exactly once across the walk. A row whose score changes moves, and this test
promises nothing about it — that is what a live ranking is.

A player walks the board over HTTP, a page at a time, while writer threads with connections of
their own raise other players' scores and add new players above and below the walker's
position. The walker waits for at least one write to commit between pages, so the writes are
known to land inside the walk rather than merely near it. Their rows are committed by other
threads and nothing can roll them back, so the test has a database of its own.
"""

from __future__ import annotations

import itertools
import random
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.community.postgres import PostgresContainer

from tests.integration.players import mint_key, serving, start_session
from wavemaker.apps.leaderboard.adapters.postgres import PostgresBoards
from wavemaker.platform.identity import players
from wavemaker.platform.persistence.engine import create_session_factory

WRITERS = 6
STABLE = 240
MOVERS = 24
LIMIT = 7
ROUNDS = 3


@pytest.fixture
def client(isolated_database_url: str) -> Iterator[TestClient]:
    with serving(isolated_database_url) as running:
        yield running


@pytest.fixture
def engine(isolated_database_url: str) -> Iterator[Engine]:
    created = create_engine(isolated_database_url, pool_size=WRITERS + 2, max_overflow=0)
    yield created
    created.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def new_player(factory: sessionmaker[Session], project: uuid.UUID) -> uuid.UUID:
    with factory() as session:
        return players.start(session, project, f"device-{uuid.uuid4()}").id


def score(
    factory: sessionmaker[Session], project: uuid.UUID, player: uuid.UUID, value: int
) -> None:
    with factory() as session:
        PostgresBoards(session, project).submit("high_score", player, value)


def test_ac4_the_walk_has_a_database_of_its_own(
    isolated_database_url: str, postgres: PostgresContainer
) -> None:
    assert isolated_database_url != postgres.get_connection_url()


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_ac4_each_unchanged_row_is_returned_exactly_once_while_scores_are_written(
    client: TestClient, factory: sessionmaker[Session], round_number: int
) -> None:
    app: Any = client.app
    project: uuid.UUID = app.state.project_id
    with factory() as session:
        PostgresBoards(session, project).save("high_score", "High score", True)

    # Many ties on purpose: five players on every score, so page boundaries fall inside them.
    stable = [new_player(factory, project) for _ in range(STABLE)]
    for index, player in enumerate(stable):
        score(factory, project, player, (index // 5) * 10)
    movers = [new_player(factory, project) for _ in range(MOVERS)]
    for player in movers:
        score(factory, project, player, 0)
    ceiling = (STABLE // 5) * 10

    headers = {"Authorization": f"Bearer {start_session(client, mint_key(client)['key'])['token']}"}
    finished = threading.Event()
    written = threading.Semaphore(0)
    writes = [0]
    lock = threading.Lock()

    def write(seed: int) -> int:
        chance = random.Random(seed)
        done = 0
        while not finished.is_set():
            if chance.random() < 0.5:
                # A mover climbs — past the walker's position or not, nobody knows which.
                score(factory, project, chance.choice(movers), chance.randrange(ceiling + 50))
            else:
                # A newcomer lands anywhere: above the walker, which shifts every row it has
                # passed, or below, where it may or may not be reached.
                score(factory, project, new_player(factory, project), chance.randrange(ceiling))
            done += 1
            with lock:
                writes[0] += 1
            written.release()
        return done

    seen: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        running = [pool.submit(write, round_number * 100 + seed) for seed in range(WRITERS)]
        try:
            cursor: str | None = None
            while True:
                query: dict[str, Any] = {"limit": LIMIT}
                if cursor is not None:
                    query["cursor"] = cursor
                response = client.get(
                    "/api/v1/player/leaderboards/high_score", params=query, headers=headers
                )
                assert response.status_code == 200, response.text
                body = response.json()
                seen.extend(body["entries"])
                cursor = body["nextCursor"]
                if cursor is None:
                    break
                # At least one write commits between every two pages.
                assert written.acquire(timeout=10), "the writers stopped writing"
        finally:
            finished.set()
            totals = [future.result() for future in running]

    pages = -(-len(seen) // LIMIT)
    assert sum(totals) >= pages - 1, "writes must have landed between the pages"

    stable_ids = {str(player) for player in stable}
    stable_seen = [entry["playerId"] for entry in seen if entry["playerId"] in stable_ids]
    assert len(stable_seen) == len(set(stable_seen)), "an unchanged row was repeated"
    assert set(stable_seen) == stable_ids, "an unchanged row was skipped"

    # And the walk only ever moves forward: each row it returns sorts strictly after the one
    # before it, by (score, player) in the board's direction, as each was when it was served.
    keys = [(entry["score"], uuid.UUID(entry["playerId"])) for entry in seen]
    assert all(later < earlier for earlier, later in itertools.pairwise(keys))
