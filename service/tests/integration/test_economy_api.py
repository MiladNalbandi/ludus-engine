"""AC-5 and AC-6: who may credit a wallet, and who may only spend from it.

That asymmetry is the whole trust model. A forged spend costs the person who forged it, so a
player may spend their own. A forged grant would make the currency whatever a modified binary
says it is, so crediting needs a credential that does not ship inside the game.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.players import ADMIN, EDITOR, VIEWER, account, player, serving
from wavemaker.apps.economy.domain.wallet import MAX_AMOUNT


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def grant(
    client: TestClient, player_id: str, amount: Any, currency: Any = "coins", email: str = EDITOR
) -> Any:
    return client.post(
        f"/api/v1/admin/players/{player_id}/wallet/grant",
        json={"currency": currency, "amount": amount},
        headers=account(client, email),
    )


def spend(client: TestClient, headers: dict[str, str], amount: Any, currency: Any = "coins") -> Any:
    return client.post(
        "/api/v1/player/me/wallet/spend",
        json={"currency": currency, "amount": amount},
        headers=headers,
    )


def wallet(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get("/api/v1/player/me/wallet", headers=headers)
    assert response.status_code == 200, response.text
    balances: list[dict[str, Any]] = response.json()["balances"]
    return balances


# --- AC-5: crediting --------------------------------------------------------------------------


def test_ac5_a_new_player_holds_nothing(client: TestClient) -> None:
    headers, _ = player(client)
    assert wallet(client, headers) == []


@pytest.mark.parametrize("email", [EDITOR, ADMIN])
def test_ac5_an_editor_grants_and_the_player_sees_it(client: TestClient, email: str) -> None:
    headers, player_id = player(client)

    granted = grant(client, player_id, 100, email=email)
    assert granted.status_code == 200
    assert granted.json()["currency"] == "coins"
    assert granted.json()["amount"] == 100
    assert granted.json()["updatedAt"].endswith("Z")

    assert grant(client, player_id, 25).json()["amount"] == 125
    assert [(b["currency"], b["amount"]) for b in wallet(client, headers)] == [("coins", 125)]


def test_ac5_a_viewer_may_look_at_nothing_and_grant_nothing(client: TestClient) -> None:
    _, player_id = player(client)
    assert grant(client, player_id, 100, email=VIEWER).status_code == 403
    response = client.get(
        f"/api/v1/admin/players/{player_id}/wallet", headers=account(client, VIEWER)
    )
    assert response.status_code == 403


def test_ac5_a_player_cannot_grant_themselves(client: TestClient) -> None:
    """Neither through the admin route with their own id, nor through a route of their own,
    because there is none."""
    headers, player_id = player(client)

    through_admin = client.post(
        f"/api/v1/admin/players/{player_id}/wallet/grant",
        json={"currency": "coins", "amount": 1_000_000},
        headers=headers,
    )
    assert through_admin.status_code == 401

    for path in ("/api/v1/player/me/wallet/grant", "/api/v1/player/me/wallet"):
        response = client.post(
            path, json={"currency": "coins", "amount": 1_000_000}, headers=headers
        )
        assert response.status_code in (404, 405), path

    assert wallet(client, headers) == []


def test_ac5_an_administrator_reads_a_players_wallet(client: TestClient) -> None:
    _, player_id = player(client)
    grant(client, player_id, 7, currency="gems")
    grant(client, player_id, 40, currency="coins")

    response = client.get(f"/api/v1/admin/players/{player_id}/wallet", headers=account(client))
    assert response.status_code == 200
    balances = response.json()["balances"]
    assert [(b["currency"], b["amount"]) for b in balances] == [("coins", 40), ("gems", 7)]


def test_ac5_currencies_are_independent(client: TestClient) -> None:
    headers, player_id = player(client)
    grant(client, player_id, 100, currency="coins")
    grant(client, player_id, 5, currency="gems")
    spend(client, headers, 30, currency="coins")

    assert [(b["currency"], b["amount"]) for b in wallet(client, headers)] == [
        ("coins", 70),
        ("gems", 5),
    ]


def test_ac5_one_players_grant_is_not_anothers(client: TestClient) -> None:
    first, first_id = player(client, "device-1")
    second, _ = player(client, "device-2")
    grant(client, first_id, 50)
    assert wallet(client, second) == []
    assert wallet(client, first)[0]["amount"] == 50


@pytest.mark.parametrize("player_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_ac5_granting_to_a_player_who_is_not_there_is_404(
    client: TestClient, player_id: str
) -> None:
    assert grant(client, player_id, 10).status_code == 404
    response = client.get(f"/api/v1/admin/players/{player_id}/wallet", headers=account(client))
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"currency": "coins", "amount": 0},
        {"currency": "coins", "amount": -10},
        {"currency": "coins", "amount": 1.5},
        {"currency": "coins", "amount": True},
        {"currency": "coins"},
        {"currency": "Gold Coins", "amount": 10},
        {"amount": 10},
    ],
)
def test_ac5_a_grant_that_is_not_one_is_refused(client: TestClient, body: dict[str, Any]) -> None:
    """A negative grant would be a spend that skipped the player, and an editor's typo."""
    _, player_id = player(client)
    response = client.post(
        f"/api/v1/admin/players/{player_id}/wallet/grant", json=body, headers=account(client)
    )
    assert response.status_code == 422


def test_ac5_a_balance_that_would_not_fit_is_refused_not_a_500(client: TestClient) -> None:
    """bigint arithmetic overflowing in the database is still the caller's mistake."""
    headers, player_id = player(client)
    assert grant(client, player_id, MAX_AMOUNT).status_code == 200

    overflowing = grant(client, player_id, 1)
    assert overflowing.status_code == 422
    assert wallet(client, headers)[0]["amount"] == MAX_AMOUNT


# --- AC-6: spending ---------------------------------------------------------------------------


def test_ac6_a_player_spends_their_own(client: TestClient) -> None:
    headers, player_id = player(client)
    grant(client, player_id, 100)

    spent = spend(client, headers, 30)
    assert spent.status_code == 200
    assert spent.json()["amount"] == 70
    assert spent.json()["currency"] == "coins"


def test_ac6_spending_exactly_the_balance_is_allowed(client: TestClient) -> None:
    headers, player_id = player(client)
    grant(client, player_id, 40)
    assert spend(client, headers, 40).json()["amount"] == 0


def test_ac6_an_overdraft_is_refused_with_422_and_leaves_the_balance_alone(
    client: TestClient,
) -> None:
    """Refused, not clamped. A spend that quietly went to zero would let a client buy what it
    cannot pay for, with this service agreeing."""
    headers, player_id = player(client)
    grant(client, player_id, 50)

    refused = spend(client, headers, 80)
    assert refused.status_code == 422
    assert "coins" in refused.json()["detail"]
    assert wallet(client, headers)[0]["amount"] == 50


def test_ac6_spending_from_nothing_is_refused(client: TestClient) -> None:
    headers, _ = player(client)
    assert spend(client, headers, 1).status_code == 422
    assert wallet(client, headers) == []


@pytest.mark.parametrize(
    "body",
    [
        {"currency": "coins", "amount": 0},
        {"currency": "coins", "amount": -10},
        {"currency": "coins", "amount": "5"},
        {"currency": "", "amount": 5},
    ],
)
def test_ac6_a_spend_that_is_not_one_is_refused(client: TestClient, body: dict[str, Any]) -> None:
    """A negative spend is a grant by another name, and the one route a player has must not be
    a way to credit themselves."""
    headers, player_id = player(client)
    grant(client, player_id, 10)
    response = client.post("/api/v1/player/me/wallet/spend", json=body, headers=headers)
    assert response.status_code == 422
    assert wallet(client, headers)[0]["amount"] == 10
