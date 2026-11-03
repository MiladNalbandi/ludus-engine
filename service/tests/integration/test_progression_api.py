"""R6 AC-6 to AC-8: the XP curve, a player's progress, and rewards that are all or nothing.

A player reads their progress and has no route that adds to it. XP a client could award itself
is XP a modified binary decides, the same reason a player cannot grant themselves currency.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.players import ADMIN, EDITOR, VIEWER, account, player, serving
from wavemaker.apps.progression.domain.curve import MAX_XP
from wavemaker.platform import currency
from wavemaker.platform.currency import Credited, CurrencyRefused

CURVE = [
    {"stage": 1, "xpRequired": 0, "label": "Rookie"},
    {"stage": 2, "xpRequired": 100, "label": "Regular"},
    {"stage": 3, "xpRequired": 250, "label": None},
]


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


class RecordingLedger:
    """A stand-in for the economy's ledger, writing inside the caller's transaction.

    It leaves a mark the test can see — the player's display name — so that whether a refused
    reward rolled the currency back is a question about a row, not about this object. It
    refuses the currency `forbidden`, as a real ledger refuses one it cannot hold.
    """

    def credit(
        self, session: Session, project: uuid.UUID, player: uuid.UUID, code: str, amount: int
    ) -> Credited:
        if code == "forbidden":
            raise CurrencyRefused(f"{code} is not a currency here")
        session.execute(
            text("update player set display_name = :mark where id = :id and project_id = :p"),
            {"mark": f"{code}:{amount}", "id": player, "p": project},
        )
        return Credited(currency=code, amount=amount, updated_at=datetime.now(UTC))


@pytest.fixture
def ledger() -> Iterator[RecordingLedger]:
    provided = currency.provided()
    recording = RecordingLedger()
    currency.provide(recording)
    yield recording
    currency.provide(provided)


@pytest.fixture
def no_ledger() -> Iterator[None]:
    provided = currency.provided()
    currency.provide(None)
    yield
    currency.provide(provided)


def put_curve(client: TestClient, stages: Any, email: str = EDITOR) -> Any:
    return client.put(
        "/api/v1/admin/xp-curve", json={"stages": stages}, headers=account(client, email)
    )


def reward(client: TestClient, player_id: str, body: Any, email: str = EDITOR) -> Any:
    return client.post(
        f"/api/v1/admin/players/{player_id}/reward", json=body, headers=account(client, email)
    )


def progress_of(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/api/v1/player/me/progress", headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def display_name(factory: sessionmaker[Session], player_id: str) -> str | None:
    with factory() as session:
        found = session.execute(
            text("select display_name from player where id = :id"), {"id": player_id}
        ).scalar_one()
    return None if found is None else str(found)


# --- AC-6: the curve ----------------------------------------------------------------------------


def test_ac6_a_project_starts_with_no_curve(client: TestClient) -> None:
    response = client.get("/api/v1/admin/xp-curve", headers=account(client, EDITOR))
    assert response.status_code == 200
    assert response.json() == {"stages": []}


@pytest.mark.parametrize("email", [EDITOR, ADMIN])
def test_ac6_an_editor_replaces_the_curve_and_gets_it_back_in_order(
    client: TestClient, email: str
) -> None:
    replaced = put_curve(client, list(reversed(CURVE)), email)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == {"stages": CURVE}
    read = client.get("/api/v1/admin/xp-curve", headers=account(client, email))
    assert read.json() == {"stages": CURVE}


def test_ac6_replacing_is_wholesale_and_an_empty_list_clears_it(client: TestClient) -> None:
    put_curve(client, CURVE)
    assert put_curve(client, [{"stage": 7, "xpRequired": 5}]).json() == {
        "stages": [{"stage": 7, "xpRequired": 5, "label": None}]
    }
    assert put_curve(client, []).json() == {"stages": []}


def test_ac6_every_problem_is_reported_at_once_at_the_index_the_request_sent(
    client: TestClient,
) -> None:
    """The Java sorted the stages and then reported the index in its sorted copy, so an author
    who sent them out of order was pointed at the wrong row."""
    response = put_curve(
        client,
        [
            {"stage": 2, "xpRequired": 100},
            {"stage": 1, "xpRequired": 200},
            {"stage": 1, "xpRequired": 300},
            {"stage": -1, "xpRequired": True, "label": "x" * 121},
        ],
    )
    assert response.status_code == 422
    problems = response.json()["detail"]
    assert "/stages/2/stage: stage 1 is listed twice" in problems
    assert any(problem.startswith("/stages/0/xpRequired") for problem in problems), problems
    assert any(problem.startswith("/stages/3/stage") for problem in problems)
    assert any(problem.startswith("/stages/3/xpRequired") for problem in problems)
    assert any(problem.startswith("/stages/3/label") for problem in problems)
    # Nothing was written.
    assert client.get("/api/v1/admin/xp-curve", headers=account(client, EDITOR)).json() == {
        "stages": []
    }


@pytest.mark.parametrize(
    "body",
    [{}, {"stages": None}, {"stages": "all of them"}, {"stages": [1, 2]}],
)
def test_ac6_a_curve_that_is_not_one_is_422(client: TestClient, body: dict[str, Any]) -> None:
    response = client.put("/api/v1/admin/xp-curve", json=body, headers=account(client, EDITOR))
    assert response.status_code == 422
    assert all(problem.startswith("/stages") for problem in response.json()["detail"])


def test_ac6_a_viewer_and_a_player_may_not_touch_the_curve(client: TestClient) -> None:
    headers, _ = player(client)
    assert put_curve(client, CURVE, VIEWER).status_code == 403
    viewer = account(client, VIEWER)
    assert client.get("/api/v1/admin/xp-curve", headers=viewer).status_code == 403
    response = client.put("/api/v1/admin/xp-curve", json={"stages": CURVE}, headers=headers)
    assert response.status_code == 401


# --- AC-7: a player's own progress -----------------------------------------------------------


def test_ac7_with_no_curve_and_no_xp_a_player_has_no_stage(client: TestClient) -> None:
    headers, _ = player(client)
    assert progress_of(client, headers) == {"xp": 0, "stage": None, "nextStage": None}


def test_ac7_the_stage_is_derived_from_xp_and_the_curve(client: TestClient) -> None:
    headers, player_id = player(client)
    put_curve(client, CURVE)
    reward(client, player_id, {"xp": 120})

    assert progress_of(client, headers) == {"xp": 120, "stage": CURVE[1], "nextStage": CURVE[2]}
    reward(client, player_id, {"xp": 130})
    assert progress_of(client, headers) == {"xp": 250, "stage": CURVE[2], "nextStage": None}


def test_ac7_editing_the_curve_moves_every_player_at_once(client: TestClient) -> None:
    """There is no stored stage to go stale."""
    headers, player_id = player(client)
    put_curve(client, CURVE)
    reward(client, player_id, {"xp": 120})
    put_curve(client, [{"stage": 1, "xpRequired": 500, "label": "First"}])

    assert progress_of(client, headers) == {
        "xp": 120,
        "stage": None,
        "nextStage": {"stage": 1, "xpRequired": 500, "label": "First"},
    }


def test_ac7_a_player_whose_row_is_gone_gets_404(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    headers, player_id = player(client)
    with session_factory() as session:
        session.execute(text("delete from player where id = :id"), {"id": player_id})
        session.commit()
    assert client.get("/api/v1/player/me/progress", headers=headers).status_code == 404


def test_ac7_no_player_route_writes_xp(client: TestClient) -> None:
    """A player can never award themselves XP: the only player route about progress reads."""
    served = client.get("/openapi.json").json()["paths"]
    writes = [
        (path, method)
        for path, operations in served.items()
        if path.startswith("/api/v1/player")
        for method in operations
        if method != "get"
    ]
    assert all("progress" not in path and "xp" not in path for path, _ in writes), writes
    assert all("reward" not in path for path, _ in writes), writes


def test_ac7_a_player_token_reaches_no_reward(client: TestClient) -> None:
    headers, player_id = player(client)
    response = client.post(
        f"/api/v1/admin/players/{player_id}/reward", json={"xp": 1_000_000}, headers=headers
    )
    assert response.status_code == 401
    assert progress_of(client, headers)["xp"] == 0


# --- AC-8: rewards ----------------------------------------------------------------------------


@pytest.mark.parametrize("email", [EDITOR, ADMIN])
def test_ac8_an_editor_rewards_xp_and_is_told_the_stage_it_reached(
    client: TestClient, email: str
) -> None:
    _, player_id = player(client)
    put_curve(client, CURVE)

    response = reward(client, player_id, {"xp": 150}, email)
    assert response.status_code == 200, response.text
    assert response.json() == {"balances": [], "xp": 150, "stage": CURVE[1]}
    assert reward(client, player_id, {"xp": 150}).json()["xp"] == 300


def test_ac8_with_no_curve_a_reward_reaches_no_stage(client: TestClient) -> None:
    _, player_id = player(client)
    assert reward(client, player_id, {"xp": 10}).json() == {
        "balances": [],
        "xp": 10,
        "stage": None,
    }


def test_ac8_a_viewer_may_not_reward(client: TestClient) -> None:
    _, player_id = player(client)
    assert reward(client, player_id, {"xp": 10}, VIEWER).status_code == 403


def test_ac8_currencies_and_xp_are_awarded_together(
    client: TestClient, ledger: RecordingLedger, session_factory: sessionmaker[Session]
) -> None:
    headers, player_id = player(client)
    response = reward(client, player_id, {"grants": [{"currency": "coins", "amount": 40}], "xp": 5})
    assert response.status_code == 200, response.text
    assert [(b["currency"], b["amount"]) for b in response.json()["balances"]] == [("coins", 40)]
    assert response.json()["balances"][0]["updatedAt"].endswith("Z")
    assert progress_of(client, headers)["xp"] == 5
    assert display_name(session_factory, player_id) == "coins:40"


def test_ac8_one_refused_grant_rolls_back_the_whole_reward_xp_included(
    client: TestClient, ledger: RecordingLedger, session_factory: sessionmaker[Session]
) -> None:
    """XP is written first and the coins second, then the second grant is refused. A player
    who kept the XP and the coins and not the rest has been given something nobody offered."""
    headers, player_id = player(client)
    response = reward(
        client,
        player_id,
        {
            "grants": [
                {"currency": "coins", "amount": 40},
                {"currency": "forbidden", "amount": 2},
            ],
            "xp": 100,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == ["/grants/1: forbidden is not a currency here"]
    assert progress_of(client, headers)["xp"] == 0
    assert display_name(session_factory, player_id) is None


def test_ac8_with_nothing_holding_currency_a_reward_with_currency_is_refused_whole(
    client: TestClient, no_ledger: None
) -> None:
    """XP without the coins would be the partial reward this route exists to prevent."""
    headers, player_id = player(client)
    response = reward(
        client, player_id, {"grants": [{"currency": "coins", "amount": 1}], "xp": 100}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0].startswith("/grants")
    assert progress_of(client, headers)["xp"] == 0


def test_ac8_a_reward_of_xp_alone_needs_nothing_to_hold_currency(
    client: TestClient, no_ledger: None
) -> None:
    _, player_id = player(client)
    assert reward(client, player_id, {"xp": 3, "grants": []}).status_code == 200


@pytest.mark.parametrize("candidate", [str(uuid.uuid4()), "not-a-uuid"])
def test_ac8_rewarding_a_player_who_is_not_there_is_404(client: TestClient, candidate: str) -> None:
    assert reward(client, candidate, {"xp": 10}).status_code == 404


def test_ac8_rewarding_a_player_of_another_project_is_404(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """The player exists, in a different project: from here that is the same as not at all."""
    with session_factory() as session:
        other = uuid.uuid4()
        session.execute(
            text(
                "insert into project (id, slug, name, created_at) values (:id, 'other', 'O', now())"
            ),
            {"id": other},
        )
        stranger = uuid.uuid4()
        session.execute(
            text("""
                insert into player (id, project_id, external_id, created_at, last_seen_at)
                values (:id, :project, 'stranger', now(), now())
            """),
            {"id": stranger, "project": other},
        )
        session.commit()
    assert reward(client, str(stranger), {"xp": 10}).status_code == 404


# --- AC-9: what a user can get wrong is a 4xx, never a 500 ------------------------------------


@pytest.mark.parametrize(
    ("body", "pointer"),
    [
        ({"xp": -1}, "/xp"),
        ({"xp": True}, "/xp"),
        ({"xp": "100"}, "/xp"),
        ({"xp": 1.5}, "/xp"),
        ({"xp": MAX_XP + 1}, "/xp"),
        ({"grants": "coins"}, "/grants"),
        ({"grants": [5]}, "/grants/0"),
        ({"grants": [{"currency": "", "amount": 1}]}, "/grants/0/currency"),
        ({"grants": [{"currency": "coins", "amount": 0}]}, "/grants/0/amount"),
        ({"grants": [{"currency": "coins", "amount": True}]}, "/grants/0/amount"),
    ],
)
def test_ac9_a_reward_that_is_not_one_is_422(
    client: TestClient, body: dict[str, Any], pointer: str
) -> None:
    _, player_id = player(client)
    response = reward(client, player_id, body)
    assert response.status_code == 422
    assert any(problem.startswith(pointer) for problem in response.json()["detail"])


def test_ac9_xp_that_would_not_fit_is_422_not_500(client: TestClient) -> None:
    headers, player_id = player(client)
    assert reward(client, player_id, {"xp": MAX_XP}).status_code == 200
    response = reward(client, player_id, {"xp": 1})
    assert response.status_code == 422
    assert "/xp" in str(response.json()["detail"])
    assert progress_of(client, headers)["xp"] == MAX_XP


@pytest.mark.parametrize("body", [[1], "xp", None])
def test_ac9_a_body_that_is_not_an_object_is_422(client: TestClient, body: Any) -> None:
    _, player_id = player(client)
    assert reward(client, player_id, body).status_code == 422
    response = client.put("/api/v1/admin/xp-curve", json=body, headers=account(client, EDITOR))
    assert response.status_code == 422
