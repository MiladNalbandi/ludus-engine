"""AC-1: API keys, which are what a game client holds.

A key is written into a config file, committed by accident and shipped inside a binary anybody
can unpack. Every rule here follows from assuming all of that happens to at least one of them:
it is shown once, stored as a digest, can never be more than a viewer, and revoking it leaves a
record of when it stopped working.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.players import EDITOR, VIEWER, account, mint_key, serving


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def test_ac1_an_administrator_mints_a_key_and_sees_it_once(client: TestClient) -> None:
    created = mint_key(client, "android-client")

    assert created["name"] == "android-client"
    assert created["role"] == "VIEWER"
    assert created["key"].startswith(created["prefix"])
    assert created["createdAt"].endswith("Z")
    uuid.UUID(created["id"])

    listed = client.get("/api/v1/admin/api-keys", headers=account(client)).json()
    assert [key["id"] for key in listed] == [created["id"]]
    assert "key" not in listed[0], "a key is shown when it is minted and never again"
    assert listed[0]["revokedAt"] is None


def test_ac1_only_a_digest_of_a_key_is_stored(client: TestClient) -> None:
    secret = mint_key(client)["key"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        stored = session.execute(text("select secret_digest from api_key")).scalars().all()
    assert secret not in stored
    assert all(len(digest) == 64 for digest in stored)


def test_ac1_two_keys_are_two_secrets(client: TestClient) -> None:
    assert mint_key(client)["key"] != mint_key(client)["key"]


def test_ac1_a_key_needs_a_name(client: TestClient) -> None:
    for body in ({}, {"name": ""}, {"name": "   "}, {"name": "x" * 121}):
        response = client.post("/api/v1/admin/api-keys", json=body, headers=account(client))
        assert response.status_code == 422, body


@pytest.mark.parametrize("email", [EDITOR, VIEWER])
def test_ac1_minting_and_revoking_keys_is_an_administrators_job(
    client: TestClient, email: str
) -> None:
    """An editor writes content; issuing credentials is a different power."""
    headers = account(client, email)
    minted = client.post("/api/v1/admin/api-keys", json={"name": "x"}, headers=headers)
    assert minted.status_code == 403
    assert client.get("/api/v1/admin/api-keys", headers=headers).status_code == 403
    key_id = mint_key(client)["id"]
    assert client.delete(f"/api/v1/admin/api-keys/{key_id}", headers=headers).status_code == 403


def test_ac1_keys_are_closed_without_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/admin/api-keys").status_code == 401


def test_ac1_revoking_stamps_the_key_and_keeps_it(client: TestClient) -> None:
    """When a key stopped working is a question asked after an incident; a deleted row cannot
    answer it."""
    key_id = mint_key(client)["id"]

    revoked = client.delete(f"/api/v1/admin/api-keys/{key_id}", headers=account(client))
    assert revoked.status_code == 200
    stamped = revoked.json()["revokedAt"]
    assert stamped and stamped.endswith("Z")

    listed = client.get("/api/v1/admin/api-keys", headers=account(client)).json()
    assert [key["revokedAt"] for key in listed] == [stamped]

    again = client.delete(f"/api/v1/admin/api-keys/{key_id}", headers=account(client))
    assert again.json()["revokedAt"] == stamped, "revoking twice must not move the record"


@pytest.mark.parametrize("key_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_ac1_revoking_a_key_that_is_not_there_is_404(client: TestClient, key_id: str) -> None:
    response = client.delete(f"/api/v1/admin/api-keys/{key_id}", headers=account(client))
    assert response.status_code == 404


def test_ac1_the_database_refuses_a_key_that_could_write(client: TestClient) -> None:
    """A key that can write is a key that can be unpacked from a game and used to write.
    Widening that is a migration and a decision, not a value somebody can set."""
    mint_key(client)
    factory = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session, pytest.raises(IntegrityError, match="ck_api_key_role"):
        session.execute(text("update api_key set role = 'EDITOR'"))
        session.commit()
