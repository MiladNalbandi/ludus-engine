"""AC-2 to AC-4: a game client trades a key for a player, and the player acts only as itself.

The key says which game is calling. It cannot say which player: it ships inside a binary, so
anything it can do, anyone who unpacked the game can do. What it buys is a short-lived token
scoped to one player, and that token is the only thing that reaches a player's state.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.players import (
    account,
    mint_key,
    player,
    serving,
    start_session,
    tokens,
)


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


# --- AC-2: a key buys a player session ------------------------------------------------------


def test_ac2_a_key_buys_a_session_for_the_games_own_player_id(client: TestClient) -> None:
    session = start_session(client, mint_key(client)["key"], "steam:76561198000000001")

    assert session["externalId"] == "steam:76561198000000001"
    assert session["displayName"] is None
    assert session["token"]
    assert session["expiresAt"].endswith("Z")
    uuid.UUID(session["playerId"])


def test_ac2_no_key_is_no_session(client: TestClient) -> None:
    response = client.post("/api/v1/public/players/session", json={"externalId": "device-1"})
    assert response.status_code == 401


def test_ac2_a_key_this_service_never_minted_is_no_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/public/players/session",
        json={"externalId": "device-1"},
        headers={"X-API-Key": "wm_" + "x" * 43},
    )
    assert response.status_code == 401


def test_ac2_a_revoked_key_buys_nothing(client: TestClient) -> None:
    """Revoking is how an operator cuts off a compromised build."""
    created = mint_key(client)
    client.delete(f"/api/v1/admin/api-keys/{created['id']}", headers=account(client))

    response = client.post(
        "/api/v1/public/players/session",
        json={"externalId": "device-1"},
        headers={"X-API-Key": created["key"]},
    )
    assert response.status_code == 401


def test_ac2_an_administrators_token_is_not_an_api_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/public/players/session",
        json={"externalId": "device-1"},
        headers=account(client),
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [{}, {"externalId": ""}, {"externalId": "   "}, {"externalId": 42}, {"externalId": "x" * 191}],
)
def test_ac2_a_session_needs_the_games_identifier(
    client: TestClient, body: dict[str, Any]
) -> None:
    response = client.post(
        "/api/v1/public/players/session", json=body, headers={"X-API-Key": mint_key(client)["key"]}
    )
    assert response.status_code == 422


def test_ac2_the_same_identifier_is_the_same_player(client: TestClient) -> None:
    """A client retrying through a network blip must find the player it just made, not make a
    second one whose progress is unreachable."""
    key = mint_key(client)["key"]
    first = start_session(client, key, "device-1")
    second = start_session(client, key, "device-1")
    other = start_session(client, key, "device-2")

    assert first["playerId"] == second["playerId"]
    assert other["playerId"] != first["playerId"]


def test_ac2_a_session_moves_last_seen(client: TestClient) -> None:
    key = mint_key(client)["key"]
    first = start_session(client, key, "device-1")
    headers = {"Authorization": f"Bearer {first['token']}"}
    seen = client.get("/api/v1/player/me", headers=headers).json()["lastSeenAt"]

    start_session(client, key, "device-1")
    again = client.get("/api/v1/player/me", headers=headers).json()

    assert datetime.fromisoformat(again["lastSeenAt"]) > datetime.fromisoformat(seen)
    assert datetime.fromisoformat(again["createdAt"]) <= datetime.fromisoformat(seen)


def test_ac2_concurrent_first_sessions_for_one_identifier_make_one_player(
    client: TestClient,
) -> None:
    """The wallet's first-grant race, one table over: several requests find no row, all insert,
    one wins. If the losers fail, a player's very first launch is an error; if they each make a
    row, there are two players. Either is the same bug."""
    key = mint_key(client)["key"]
    gate = threading.Barrier(8)

    def begin(_: int) -> tuple[int, str]:
        gate.wait()
        response = client.post(
            "/api/v1/public/players/session",
            json={"externalId": "a-brand-new-device"},
            headers={"X-API-Key": key},
        )
        return response.status_code, response.json().get("playerId", "")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(begin, range(8)))

    assert {status for status, _ in results} == {200}
    assert len({player_id for _, player_id in results}) == 1
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        assert session.execute(text("select count(*) from player")).scalar_one() == 1


# --- AC-3: the kinds of token do not cross ---------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/me"),
        ("GET", "/api/v1/admin/waves"),
        ("GET", "/api/v1/admin/api-keys"),
        ("POST", "/api/v1/admin/api-keys"),
        ("GET", "/api/v1/admin/players/{player}/wallet"),
        ("POST", "/api/v1/admin/players/{player}/wallet/grant"),
    ],
)
def test_ac3_a_player_token_reaches_no_administrative_route(
    client: TestClient, method: str, path: str
) -> None:
    headers, player_id = player(client)
    response = client.request(
        method,
        path.format(player=player_id),
        headers=headers,
        json={"name": "x", "currency": "coins", "amount": 1},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/player/me"),
        ("PATCH", "/api/v1/player/me"),
        ("GET", "/api/v1/player/me/wallet"),
        ("POST", "/api/v1/player/me/wallet/spend"),
    ],
)
@pytest.mark.parametrize("kind", ["accessToken", "refreshToken"])
def test_ac3_an_administrators_token_reaches_no_player_route(
    client: TestClient, method: str, path: str, kind: str
) -> None:
    """Not even as the player whose uuid it might carry. An administrator acting on a player
    does it through an admin route, which says who did it."""
    player(client)
    token = tokens(client)[kind]
    response = client.request(
        method,
        path,
        headers={"Authorization": f"Bearer {token}"},
        json={"displayName": "x", "currency": "coins", "amount": 1},
    )
    assert response.status_code == 401


def test_ac3_an_api_key_cannot_touch_player_state_directly(client: TestClient) -> None:
    """The reason the session exists. A key that could write player state is every player's
    state, written by anybody who unpacked the game."""
    key = mint_key(client)["key"]
    for headers in ({"X-API-Key": key}, {"Authorization": f"Bearer {key}"}):
        assert client.get("/api/v1/player/me", headers=headers).status_code == 401
        assert client.get("/api/v1/player/me/wallet", headers=headers).status_code == 401
        spend = client.post(
            "/api/v1/player/me/wallet/spend",
            headers=headers,
            json={"currency": "coins", "amount": 1},
        )
        assert spend.status_code == 401


def test_ac3_player_routes_need_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/player/me").status_code == 401
    assert client.get("/api/v1/player/me/wallet").status_code == 401


# --- AC-4: /me, and only /me ----------------------------------------------------------------


def test_ac4_a_player_reads_themselves(client: TestClient) -> None:
    headers, player_id = player(client, "device-42")
    response = client.get("/api/v1/player/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == player_id
    assert body["externalId"] == "device-42"
    assert body["displayName"] is None
    assert body["createdAt"].endswith("Z")
    assert body["lastSeenAt"].endswith("Z")


def test_ac4_a_player_names_and_unnames_themselves(client: TestClient) -> None:
    headers, _ = player(client)

    named = client.patch("/api/v1/player/me", headers=headers, json={"displayName": "  Alex "})
    assert named.status_code == 200
    assert named.json()["displayName"] == "Alex"
    assert client.get("/api/v1/player/me", headers=headers).json()["displayName"] == "Alex"

    cleared = client.patch("/api/v1/player/me", headers=headers, json={"displayName": "  "})
    assert cleared.json()["displayName"] is None


def test_ac4_names_are_not_unique(client: TestClient) -> None:
    first, _ = player(client, "device-1")
    second, _ = player(client, "device-2")
    for headers in (first, second):
        response = client.patch("/api/v1/player/me", headers=headers, json={"displayName": "Alex"})
        assert response.status_code == 200


@pytest.mark.parametrize("name", [42, "x" * 121])
def test_ac4_a_name_that_is_not_one_is_refused(client: TestClient, name: object) -> None:
    headers, _ = player(client)
    response = client.patch("/api/v1/player/me", headers=headers, json={"displayName": name})
    assert response.status_code == 422


def test_ac4_two_players_see_only_themselves(client: TestClient) -> None:
    first, first_id = player(client, "device-1")
    second, second_id = player(client, "device-2")
    assert client.get("/api/v1/player/me", headers=first).json()["id"] == first_id
    assert client.get("/api/v1/player/me", headers=second).json()["id"] == second_id


def test_ac4_a_player_removed_mid_session_is_404_not_401(client: TestClient) -> None:
    """The token is still valid; the player is gone. The credential is not the problem."""
    headers, player_id = player(client)
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        session.execute(text("delete from player where id = :id"), {"id": player_id})
        session.commit()
    assert client.get("/api/v1/player/me", headers=headers).status_code == 404


def test_ac4_no_player_route_takes_a_player_id(client: TestClient) -> None:
    """A route shaped /players/{id} authorised by "is a player" is a route on which any player
    can act as any other, and the check that stops it is one somebody must remember to write in
    every handler. With no id in the path there is nothing to forget."""
    served = client.get("/openapi.json").json()["paths"]
    player_paths = [path for path in served if path.startswith("/api/v1/player")]
    assert player_paths, "the player routes must be mounted"
    assert all("{" not in path for path in player_paths), player_paths


# --- the frozen contract ----------------------------------------------------------------------

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi-v1.json"


def fields_of(schema: str) -> set[str]:
    document: dict[str, Any] = json.loads(CONTRACT.read_text())
    return set(document["components"]["schemas"][schema]["properties"])


def test_every_player_and_key_body_spells_its_fields_the_way_the_contract_does(
    client: TestClient,
) -> None:
    """Generated clients are built from the frozen document. A field added, dropped or renamed
    here is a client broken in the field, with nothing on this side failing."""
    created = mint_key(client)
    session = start_session(client, created["key"])
    headers = {"Authorization": f"Bearer {session['token']}"}
    admin = account(client)
    client.post(
        f"/api/v1/admin/players/{session['playerId']}/wallet/grant",
        json={"currency": "coins", "amount": 5},
        headers=admin,
    )
    spent = client.post(
        "/api/v1/player/me/wallet/spend", json={"currency": "coins", "amount": 1}, headers=headers
    ).json()
    wallet = client.get("/api/v1/player/me/wallet", headers=headers).json()
    profile = client.get("/api/v1/player/me", headers=headers).json()
    listed = client.get("/api/v1/admin/api-keys", headers=admin).json()

    assert set(created) == fields_of("ApiKeyCreated")
    assert set(listed[0]) == fields_of("ApiKeySummary")
    assert set(session) == fields_of("PlayerSession")
    assert set(profile) == fields_of("PlayerProfile")
    assert set(wallet) == fields_of("PlayerWallet")
    assert set(wallet["balances"][0]) == fields_of("PlayerBalance")
    assert set(spent) == fields_of("PlayerBalance")
