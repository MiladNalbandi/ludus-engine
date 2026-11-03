"""R6 AC-1 to AC-3 and AC-9: boards, scores a player submits for themselves, and keyset pages.

The walk under concurrent writes — the criterion R6 is done by — has a file and a database of
its own, `test_leaderboard_concurrency.py`. What is here is the rest of the contract, and the
same walk with the writes interleaved between pages, where the result is deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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


def a_player(client: TestClient, key: str, name: str | None = None) -> tuple[dict[str, str], str]:
    """A player of their own, optionally named, and that player's headers and id."""
    session = start_session(client, key, f"device-{uuid.uuid4()}")
    headers = {"Authorization": f"Bearer {session['token']}"}
    if name is not None:
        answer = client.patch("/api/v1/player/me", headers=headers, json={"displayName": name})
        assert answer
    return headers, str(session["playerId"])


def save_board(client: TestClient, board: str, body: Any = None, email: str = EDITOR) -> Any:
    return client.put(
        f"/api/v1/admin/leaderboards/{board}",
        json={"name": "High score"} if body is None else body,
        headers=account(client, email),
    )


def submit(client: TestClient, headers: dict[str, str], board: str, score: Any) -> Any:
    return client.post(
        f"/api/v1/player/leaderboards/{board}/me", json={"score": score}, headers=headers
    )


def page(client: TestClient, headers: dict[str, str], board: str, **query: Any) -> dict[str, Any]:
    response = client.get(f"/api/v1/player/leaderboards/{board}", params=query, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def walk(
    client: TestClient,
    headers: dict[str, str],
    board: str,
    limit: int,
    between: Any = None,
) -> list[dict[str, Any]]:
    """Every entry, a page at a time, calling `between` after each page."""
    seen: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(1000):
        query: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            query["cursor"] = cursor
        body = page(client, headers, board, **query)
        seen.extend(body["entries"])
        cursor = body["nextCursor"]
        if cursor is None:
            return seen
        if between is not None:
            between()
    raise AssertionError("the walk never ended")


# --- AC-1: an editor defines boards -----------------------------------------------------------


@pytest.mark.parametrize("email", [EDITOR, ADMIN])
def test_ac1_an_editor_creates_a_board_that_is_descending_unless_it_says_not(
    client: TestClient, email: str
) -> None:
    created = save_board(client, "high_score", email=email)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["id"] == "high_score"
    assert body["name"] == "High score"
    assert body["descending"] is True
    assert body["createdAt"].endswith("Z")
    assert body["updatedAt"].endswith("Z")

    lap = save_board(client, "lap_time", {"name": "Lap time", "descending": False}).json()
    assert lap["descending"] is False


def test_ac1_saving_again_replaces_the_name_and_direction_and_keeps_the_creation_time(
    client: TestClient,
) -> None:
    first = save_board(client, "high_score").json()
    second = save_board(client, "high_score", {"name": "Best", "descending": False}).json()
    assert second["name"] == "Best"
    assert second["descending"] is False
    assert second["createdAt"] == first["createdAt"]


def test_ac1_boards_are_listed_by_id_to_editors_and_players(client: TestClient, key: str) -> None:
    save_board(client, "zeta")
    save_board(client, "alpha")
    headers, _ = a_player(client, key)

    as_editor = client.get("/api/v1/admin/leaderboards", headers=account(client, EDITOR))
    as_player = client.get("/api/v1/player/leaderboards", headers=headers)
    assert [board["id"] for board in as_editor.json()] == ["alpha", "zeta"]
    assert as_player.json() == as_editor.json()


def test_ac1_a_viewer_may_neither_define_nor_read_a_board_as_an_administrator(
    client: TestClient,
) -> None:
    save_board(client, "high_score")
    viewer = account(client, VIEWER)
    assert save_board(client, "other", email=VIEWER).status_code == 403
    assert client.get("/api/v1/admin/leaderboards", headers=viewer).status_code == 403
    assert client.get("/api/v1/admin/leaderboards/high_score", headers=viewer).status_code == 403
    answer = client.delete("/api/v1/admin/leaderboards/high_score", headers=viewer)
    assert answer.status_code == 403


def test_ac1_a_player_may_not_define_a_board(client: TestClient, key: str) -> None:
    headers, _ = a_player(client, key)
    response = client.put("/api/v1/admin/leaderboards/mine", json={"name": "Mine"}, headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("board", "body", "pointer"),
    [
        ("High-Score", {"name": "x"}, "/boardId"),
        ("a" * 65, {"name": "x"}, "/boardId"),
        ("high_score", {}, "/name"),
        ("high_score", {"name": "   "}, "/name"),
        ("high_score", {"name": 7}, "/name"),
        ("high_score", {"name": "x" * 256}, "/name"),
        ("high_score", {"name": "x", "descending": "false"}, "/descending"),
    ],
)
def test_ac1_a_board_that_is_not_one_is_refused_with_422(
    client: TestClient, board: str, body: dict[str, Any], pointer: str
) -> None:
    response = save_board(client, board, body)
    assert response.status_code == 422
    assert pointer in response.json()["detail"]


def test_ac1_deleting_a_board_takes_its_scores_with_it(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    submit(client, headers, "high_score", 10)
    editor = account(client, EDITOR)

    answer = client.delete("/api/v1/admin/leaderboards/high_score", headers=editor)
    assert answer.status_code == 204
    answer = client.delete("/api/v1/admin/leaderboards/high_score", headers=editor)
    assert answer.status_code == 404
    save_board(client, "high_score")
    assert page(client, headers, "high_score")["total"] == 0


# --- AC-2: a player submits their own score, and only their own ---------------------------------


def test_ac2_a_player_submits_and_sees_where_they_stand(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    headers, player_id = a_player(client, key, "Alex")

    submitted = submit(client, headers, "high_score", 1200)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["playerId"] == player_id
    assert submitted.json()["displayName"] == "Alex"
    assert submitted.json()["score"] == 1200
    assert submitted.json()["rank"] == 1
    mine = client.get("/api/v1/player/leaderboards/high_score/me", headers=headers)
    assert mine.json() == submitted.json()


def test_ac2_the_better_score_is_kept_in_the_boards_own_direction(
    client: TestClient, key: str
) -> None:
    save_board(client, "high_score")
    save_board(client, "lap_time", {"name": "Lap", "descending": False})
    headers, _ = a_player(client, key)

    assert submit(client, headers, "high_score", 500).json()["score"] == 500
    assert submit(client, headers, "high_score", 300).json()["score"] == 500, "a worse round"
    assert submit(client, headers, "high_score", 900).json()["score"] == 900

    assert submit(client, headers, "lap_time", 61_000).json()["score"] == 61_000
    assert submit(client, headers, "lap_time", 75_000).json()["score"] == 61_000
    assert submit(client, headers, "lap_time", 58_500).json()["score"] == 58_500


def test_ac2_an_equal_score_keeps_the_time_it_was_first_reached(
    client: TestClient, key: str
) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    first = submit(client, headers, "high_score", 500).json()
    again = submit(client, headers, "high_score", 500).json()
    assert again["updatedAt"] == first["updatedAt"]


def test_ac2_a_player_id_in_the_body_writes_nobody_elses_score(
    client: TestClient, key: str
) -> None:
    save_board(client, "high_score")
    headers, mine = a_player(client, key)
    victim_headers, victim = a_player(client, key)

    response = client.post(
        "/api/v1/player/leaderboards/high_score/me",
        json={"score": 999, "playerId": victim},
        headers=headers,
    )
    assert response.json()["playerId"] == mine
    assert (
        client.get("/api/v1/player/leaderboards/high_score/me", headers=victim_headers).status_code
        == 404
    )


def test_ac2_a_player_with_no_score_has_no_entry(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    response = client.get("/api/v1/player/leaderboards/high_score/me", headers=headers)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/player/leaderboards"),
        ("GET", "/api/v1/player/leaderboards/high_score"),
        ("GET", "/api/v1/player/leaderboards/high_score/me"),
        ("POST", "/api/v1/player/leaderboards/high_score/me"),
    ],
)
def test_ac2_the_player_routes_need_a_player_token_and_refuse_an_administrators(
    client: TestClient, method: str, path: str
) -> None:
    save_board(client, "high_score")
    for headers in ({}, account(client, ADMIN)):
        response = client.request(method, path, headers=headers, json={"score": 1})
        assert response.status_code == 401


def test_ac2_an_administrator_cannot_submit_through_a_player_route_for_a_player(
    client: TestClient, key: str
) -> None:
    """There is no admin route that writes a score either: the only writer is the player."""
    served = client.get("/openapi.json").json()["paths"]
    writes = [
        (path, method)
        for path, operations in served.items()
        if "leaderboards" in path
        for method in operations
        if method in ("post", "patch")
    ]
    assert writes == [("/api/v1/player/leaderboards/{boardId}/me", "post")]


def test_ac2_a_player_whose_row_is_gone_gets_404_not_500(
    client: TestClient, key: str, session_factory: Any
) -> None:
    save_board(client, "high_score")
    headers, player_id = a_player(client, key)
    with session_factory() as session:
        session.execute(text("delete from player where id = :id"), {"id": player_id})
        session.commit()
    assert submit(client, headers, "high_score", 10).status_code == 404


# --- AC-3: pages are keyset, in rank order, over a total order ---------------------------------


def test_ac3_a_board_pages_in_rank_order_with_ranks_that_continue(
    client: TestClient, key: str
) -> None:
    save_board(client, "high_score")
    scores = [40, 10, 90, 70, 20, 60]
    for score in scores:
        submit(client, a_player(client, key)[0], "high_score", score)
    headers, _ = a_player(client, key)

    entries = walk(client, headers, "high_score", 4)
    assert [entry["score"] for entry in entries] == sorted(scores, reverse=True)
    assert [entry["rank"] for entry in entries] == [1, 2, 3, 4, 5, 6]
    assert page(client, headers, "high_score", limit=4)["total"] == 6


def test_ac3_an_ascending_board_ranks_the_smallest_first(client: TestClient, key: str) -> None:
    save_board(client, "lap_time", {"name": "Lap", "descending": False})
    for score in [61_000, 58_500, 75_000]:
        submit(client, a_player(client, key)[0], "lap_time", score)
    headers, _ = a_player(client, key)

    entries = walk(client, headers, "lap_time", 2)
    assert [entry["score"] for entry in entries] == [58_500, 61_000, 75_000]


def test_ac3_tied_scores_are_still_a_total_order_so_a_walk_neither_repeats_nor_skips(
    client: TestClient, key: str
) -> None:
    """Everybody who finished the tutorial has the same score. Without the player id breaking
    the tie, a cursor sits in the middle of it and cannot say which of them it has passed."""
    save_board(client, "high_score")
    tied = sorted((a_player(client, key) for _ in range(12)), key=lambda pair: pair[1])
    for headers, _ in tied:
        submit(client, headers, "high_score", 100)

    entries = walk(client, tied[0][0], "high_score", 5)
    ids = [entry["playerId"] for entry in entries]
    assert sorted(ids) == sorted(player_id for _, player_id in tied)
    assert len(set(ids)) == 12
    # The tie-break is the player id, descending with the board: a stable, documented order.
    assert ids == sorted(ids, key=uuid.UUID, reverse=True)


def test_ac3_a_players_own_rank_is_where_the_pages_put_them(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    players = [a_player(client, key) for _ in range(9)]
    for index, (headers, _) in enumerate(players):
        submit(client, headers, "high_score", (index % 3) * 10)

    entries = walk(client, players[0][0], "high_score", 4)
    for headers, player_id in players:
        mine = client.get("/api/v1/player/leaderboards/high_score/me", headers=headers).json()
        assert entries[mine["rank"] - 1]["playerId"] == player_id


def test_ac3_a_walk_returns_each_unchanged_row_once_while_others_move_between_pages(
    client: TestClient, key: str
) -> None:
    """The criterion with the writes put between pages, so the outcome is deterministic.

    Twenty players hold still while two others climb past them after every page, and a new
    player arrives at the top each time. An offset walk repeats rows here on every page, because
    every row it has already served moves down one place for each arrival above it.
    """
    save_board(client, "high_score")
    stable = []
    for index in range(20):
        headers, player_id = a_player(client, key)
        submit(client, headers, "high_score", 1000 - (index // 2) * 10)  # in pairs: ties too
        stable.append(player_id)
    churn = [a_player(client, key) for _ in range(2)]
    for headers, _ in churn:
        submit(client, headers, "high_score", 5)

    rounds = [0]

    def others_write() -> None:
        rounds[0] += 1
        submit(client, churn[0][0], "high_score", 2000 + rounds[0])
        submit(client, churn[1][0], "high_score", 3000 + rounds[0])
        submit(client, a_player(client, key)[0], "high_score", 5000 + rounds[0])

    seen = walk(client, churn[0][0], "high_score", 5, between=others_write)
    stable_seen = [entry["playerId"] for entry in seen if entry["playerId"] in stable]
    assert sorted(stable_seen) == sorted(stable), "every unchanged row, each exactly once"
    assert rounds[0] >= 3, "the writes must actually have happened between pages"


def test_ac3_a_page_carries_the_board_and_a_cursor_only_while_there_is_more(
    client: TestClient, key: str
) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    submit(client, headers, "high_score", 1)

    body = page(client, headers, "high_score")
    assert body["board"]["id"] == "high_score"
    assert body["nextCursor"] is None
    assert body["total"] == 1


def test_ac3_an_editor_walks_a_board_as_a_player_does(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    for score in range(5):
        submit(client, a_player(client, key)[0], "high_score", score)
    editor = account(client, EDITOR)

    first = client.get("/api/v1/admin/leaderboards/high_score?limit=3", headers=editor).json()
    rest = client.get(
        "/api/v1/admin/leaderboards/high_score",
        params={"limit": 3, "cursor": first["nextCursor"]},
        headers=editor,
    ).json()
    scores = [entry["score"] for entry in first["entries"] + rest["entries"]]
    assert scores == [4, 3, 2, 1, 0]
    assert rest["nextCursor"] is None


def test_ac3_a_page_is_never_larger_than_the_cap(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    submit(client, headers, "high_score", 1)
    assert len(page(client, headers, "high_score", limit=10_000)["entries"]) == 1
    assert len(page(client, headers, "high_score", limit=0)["entries"]) == 1


def test_ac3_a_deleted_player_leaves_the_board(
    client: TestClient, key: str, session_factory: Any
) -> None:
    save_board(client, "high_score")
    headers, mine = a_player(client, key)
    gone_headers, gone = a_player(client, key)
    submit(client, headers, "high_score", 1)
    submit(client, gone_headers, "high_score", 2)
    with session_factory() as session:
        session.execute(text("delete from player where id = :id"), {"id": gone})
        session.commit()
    body = page(client, headers, "high_score")
    assert [entry["playerId"] for entry in body["entries"]] == [mine]
    assert body["total"] == 1


# --- AC-9: what a user can get wrong is a 4xx, never a 500 ------------------------------------


@pytest.mark.parametrize("score", [None, "100", 1.5, True, 2**63, -(2**63) - 1, [1], {"value": 1}])
def test_ac9_a_score_that_is_not_one_is_422(client: TestClient, key: str, score: Any) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    response = submit(client, headers, "high_score", score)
    assert response.status_code == 422
    assert "/score" in response.json()["detail"]


@pytest.mark.parametrize("score", [2**63 - 1, -(2**63), 0, -5])
def test_ac9_every_score_a_bigint_holds_is_accepted(
    client: TestClient, key: str, score: int
) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    assert submit(client, headers, "high_score", score).json()["score"] == score


@pytest.mark.parametrize("board", ["no_such_board", "Not-A-Board", "x" * 100])
def test_ac9_a_board_that_is_not_there_is_404_on_every_route(
    client: TestClient, key: str, board: str
) -> None:
    headers, _ = a_player(client, key)
    editor = account(client, EDITOR)
    assert submit(client, headers, board, 1).status_code == 404
    assert client.get(f"/api/v1/player/leaderboards/{board}", headers=headers).status_code == 404
    response = client.get(f"/api/v1/player/leaderboards/{board}/me", headers=headers)
    assert response.status_code == 404
    assert client.get(f"/api/v1/admin/leaderboards/{board}", headers=editor).status_code == 404
    answer = client.delete(f"/api/v1/admin/leaderboards/{board}", headers=editor)
    assert answer.status_code == 404


@pytest.mark.parametrize(
    "cursor",
    [
        "not-a-cursor",
        "%%%",
        paging.encode_cursor("ten", str(uuid.uuid4())),
        paging.encode_cursor("10", "not-a-uuid"),
        paging.encode_cursor(str(2**70), str(uuid.uuid4())),
        paging.encode_cursor("10"),
        paging.encode_cursor("10", str(uuid.uuid4()), "extra"),
    ],
)
def test_ac9_a_cursor_this_service_did_not_issue_is_422_not_the_first_page(
    client: TestClient, key: str, cursor: str
) -> None:
    """Not the first page, as the Java answered: a client quietly sent back to the start sees
    every row twice and cannot tell."""
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    response = client.get(
        "/api/v1/player/leaderboards/high_score", params={"cursor": cursor}, headers=headers
    )
    assert response.status_code == 422
    assert "/cursor" in str(response.json()["detail"])


def test_ac9_a_limit_that_is_not_a_number_is_422(client: TestClient, key: str) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    response = client.get("/api/v1/player/leaderboards/high_score?limit=ten", headers=headers)
    assert response.status_code == 422


@pytest.mark.parametrize("body", [[1, 2], "100", None])
def test_ac9_a_body_that_is_not_an_object_is_422(client: TestClient, key: str, body: Any) -> None:
    save_board(client, "high_score")
    headers, _ = a_player(client, key)
    response = client.post("/api/v1/player/leaderboards/high_score/me", json=body, headers=headers)
    assert response.status_code == 422
    saved = client.put(
        "/api/v1/admin/leaderboards/high_score", json=body, headers=account(client, EDITOR)
    )
    assert saved.status_code == 422
