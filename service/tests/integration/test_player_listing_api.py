"""R6 AC-5: an editor lists players with the same keyset paging as a board, and reads one.

`last_seen_at` moves every time somebody plays, so it is the ordering column most in need of a
keyset: an offset walk over it repeats and skips players under any traffic at all. The same
guarantee as a board's, and no more: a player who is not seen during a walk is listed exactly
once, and one who starts a session moves to the front.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.players import (
    ADMIN,
    EDITOR,
    VIEWER,
    account,
    mint_key,
    serving,
    start_session,
)
from wavemaker.platform import paging


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


@pytest.fixture
def key(client: TestClient) -> str:
    return str(mint_key(client)["key"])


def new_player(client: TestClient, key: str, external_id: str | None = None) -> str:
    session = start_session(client, key, external_id or f"device-{uuid.uuid4()}")
    return str(session["playerId"])


def listing(client: TestClient, email: str = EDITOR, **query: Any) -> Any:
    return client.get("/api/v1/admin/players", params=query, headers=account(client, email))


def walk(client: TestClient, limit: int, between: Any = None) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(1000):
        query: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            query["cursor"] = cursor
        response = listing(client, **query)
        assert response.status_code == 200, response.text
        seen.extend(response.json()["players"])
        cursor = response.json()["nextCursor"]
        if cursor is None:
            return seen
        if between is not None:
            between()
    raise AssertionError("the walk never ended")


def seen_at(factory: sessionmaker[Session], moments: dict[str, datetime]) -> None:
    with factory() as session:
        for player_id, moment in moments.items():
            session.execute(
                text("update player set last_seen_at = :at where id = :id"),
                {"at": moment, "id": player_id},
            )
        session.commit()


# --- AC-5: listing --------------------------------------------------------------------------


@pytest.mark.parametrize("email", [EDITOR, ADMIN])
def test_ac5_an_editor_lists_players_most_recently_seen_first(
    client: TestClient, key: str, email: str
) -> None:
    first, second, third = (new_player(client, key, f"device-{n}") for n in range(3))
    start_session(client, key, "device-0")  # the first plays again, and is now the latest

    response = listing(client, email)
    assert response.status_code == 200, response.text
    assert [player["id"] for player in response.json()["players"]] == [first, third, second]
    assert response.json()["total"] == 3
    assert response.json()["nextCursor"] is None


def test_ac5_a_viewer_and_a_player_may_not_list_players(client: TestClient, key: str) -> None:
    session = start_session(client, key)
    assert listing(client, VIEWER).status_code == 403
    as_player = client.get(
        "/api/v1/admin/players", headers={"Authorization": f"Bearer {session['token']}"}
    )
    assert as_player.status_code == 401
    assert client.get("/api/v1/admin/players").status_code == 401


def test_ac5_players_seen_at_the_same_moment_are_still_a_total_order(
    client: TestClient, key: str, session_factory: sessionmaker[Session]
) -> None:
    """A batch import, or a clock with coarse resolution: many players, one timestamp. Without
    the id breaking the tie, a cursor lands inside it and repeats or skips players."""
    ids = [new_player(client, key) for _ in range(11)]
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    seen_at(session_factory, dict.fromkeys(ids, moment))

    walked = [player["id"] for player in walk(client, 3)]
    assert sorted(walked) == sorted(ids)
    assert walked == sorted(ids, key=uuid.UUID, reverse=True)


def test_ac5_the_cursor_keeps_microseconds_so_a_millisecond_does_not_hide_a_player(
    client: TestClient, key: str, session_factory: sessionmaker[Session]
) -> None:
    """The Java's cursor carried epoch milliseconds. Of two players seen in one millisecond on
    either side of a page boundary, the second compared against a truncated cursor as if it
    were newer than it, and was never listed."""
    earlier, later = new_player(client, key), new_player(client, key)
    millisecond = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    seen_at(
        session_factory,
        {
            later: millisecond + timedelta(microseconds=900),
            earlier: millisecond + timedelta(microseconds=400),
        },
    )

    assert [player["id"] for player in walk(client, 1)] == [later, earlier]


def test_ac5_a_walk_lists_each_player_not_seen_meanwhile_exactly_once(
    client: TestClient, key: str
) -> None:
    """Between every page, two players start a session and a new one arrives. All three move to
    the front, which the walk has passed; an offset walk would serve the players it has already
    listed again, one for each arrival above them."""
    still = [new_player(client, key, f"still-{index}") for index in range(16)]
    restless = [f"restless-{index}" for index in range(4)]
    for external_id in restless:
        new_player(client, key, external_id)
    rounds = [0]

    def others_play() -> None:
        rounds[0] += 1
        start_session(client, key, restless[rounds[0] % len(restless)])
        start_session(client, key, restless[(rounds[0] + 1) % len(restless)])
        new_player(client, key)

    walked = [player["id"] for player in walk(client, 4, between=others_play)]
    listed = [player_id for player_id in walked if player_id in still]
    assert sorted(listed) == sorted(still), "every player not seen meanwhile, exactly once"
    assert rounds[0] >= 3


def test_ac5_a_page_is_capped_and_a_limit_below_one_is_one(client: TestClient, key: str) -> None:
    for _ in range(3):
        new_player(client, key)
    assert len(listing(client, limit=1).json()["players"]) == 1
    assert len(listing(client, limit=0).json()["players"]) == 1
    assert len(listing(client, limit=10_000).json()["players"]) == 3


@pytest.mark.parametrize(
    "cursor",
    [
        "garbage",
        paging.encode_cursor("yesterday", str(uuid.uuid4())),
        paging.encode_cursor("2026-01-01T00:00:00", str(uuid.uuid4())),  # no zone
        paging.encode_cursor("2026-01-01T00:00:00+00:00", "nobody"),
        paging.encode_cursor("2026-01-01T00:00:00+00:00"),
    ],
)
def test_ac5_a_cursor_this_service_did_not_issue_is_422(client: TestClient, cursor: str) -> None:
    response = listing(client, cursor=cursor)
    assert response.status_code == 422
    assert "/cursor" in response.json()["detail"]


def test_ac5_a_limit_that_is_not_a_number_is_422(client: TestClient) -> None:
    assert listing(client, limit="lots").status_code == 422


# --- AC-5: one player -------------------------------------------------------------------------


def test_ac5_an_editor_reads_one_player(client: TestClient, key: str) -> None:
    player_id = new_player(client, key, "steam:1")
    response = client.get(f"/api/v1/admin/players/{player_id}", headers=account(client, EDITOR))
    assert response.status_code == 200
    assert response.json()["id"] == player_id
    assert response.json()["externalId"] == "steam:1"


@pytest.mark.parametrize("candidate", [str(uuid.uuid4()), "not-a-uuid", "1"])
def test_ac5_a_player_who_is_not_there_is_404(client: TestClient, candidate: str) -> None:
    response = client.get(f"/api/v1/admin/players/{candidate}", headers=account(client, EDITOR))
    assert response.status_code == 404


def test_ac5_a_viewer_may_not_read_a_player(client: TestClient, key: str) -> None:
    player_id = new_player(client, key)
    response = client.get(f"/api/v1/admin/players/{player_id}", headers=account(client, VIEWER))
    assert response.status_code == 403
