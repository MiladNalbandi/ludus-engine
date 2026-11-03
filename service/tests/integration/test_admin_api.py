"""The authoring surface, against a real database and real credentials.

These routes decide what every player receives, so the first thing each test establishes is
that they cannot be reached without the right role.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.identity.accounts import ensure_account
from wavemaker.platform.identity.tokens import Role

SECRET = "an-authoring-test-signing-key-of-respectable-length"  # keel:allow-secret
ADMIN = "admin@example.test"
PASSWORD = "correct-horse-battery-staple"  # keel:allow-secret
VIEWER = "viewer@example.test"

SAMPLES = Path(__file__).resolve().parents[3] / "samples" / "waves"


def a_document(wave_id: str = "demo_first_steps", order: int | None = None) -> bytes:
    """A real sample, so these tests fail if the shipped content stops validating."""
    document: dict[str, Any] = json.loads((SAMPLES / "demo_first_steps.json").read_text())
    document["id"] = wave_id
    if order is not None:
        document["progression_config"]["order"] = order
    # Compact and with the keys in this order, so "the bytes came back unchanged" is a real
    # claim rather than one that survives a reformat by luck.
    return json.dumps(document, separators=(",", ":")).encode()


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            plugins_directory=None,
            database_url=database_url,
            jwt_secret=SECRET,
            admin_email=ADMIN,
            admin_password=PASSWORD,
        )
    )
    with app.state.session_factory() as session:
        ensure_account(session, app.state.project_id, VIEWER, PASSWORD, Role.VIEWER)
    with TestClient(app) as running:
        yield running


def token(client: TestClient, email: str = ADMIN) -> str:
    response = client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return str(response.json()["accessToken"])


def admin(client: TestClient, email: str = ADMIN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(client, email)}"}


# --- who may reach these routes ------------------------------------------------------------


def test_authoring_is_closed_without_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/admin/waves").status_code == 401
    assert client.post("/api/v1/admin/waves", content=a_document()).status_code == 401


def test_a_viewer_may_read_drafts_but_not_change_them(client: TestClient) -> None:
    """The role split, which is the only reason a viewer role exists at all."""
    headers = admin(client, VIEWER)
    assert client.get("/api/v1/admin/waves", headers=headers).status_code == 200
    assert (
        client.post("/api/v1/admin/waves", content=a_document(), headers=headers).status_code == 403
    )


def test_a_public_route_still_needs_no_credential(client: TestClient) -> None:
    """Authoring moved behind a role. Serving must not have followed it."""
    assert client.get("/api/v1/public/waves").status_code == 200


# --- authoring ------------------------------------------------------------------------------


def test_a_wave_is_created_and_comes_back_in_the_list(client: TestClient) -> None:
    created = client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    assert created.status_code == 201, created.text
    assert created.json()["published"] is False, "a new wave is a draft"

    listed = client.get("/api/v1/admin/waves", headers=admin(client)).json()
    assert [wave["id"] for wave in listed] == ["demo_first_steps"]


def test_the_document_comes_back_byte_for_byte(client: TestClient) -> None:
    body = a_document()
    client.post("/api/v1/admin/waves", content=body, headers=admin(client))
    fetched = client.get("/api/v1/admin/waves/demo_first_steps", headers=admin(client))
    assert fetched.content == body


def test_creating_the_same_wave_twice_is_a_conflict(client: TestClient) -> None:
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    again = client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    assert again.status_code == 409


def test_replacing_a_wave_keeps_its_publication_state(client: TestClient) -> None:
    """A save is not a publish. If it were, the only way to fix a live wave would be to
    delete it."""
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    client.post("/api/v1/admin/waves/demo_first_steps/publish", headers=admin(client))

    replaced = client.put(
        "/api/v1/admin/waves/demo_first_steps",
        content=a_document(),
        headers=admin(client),
    )
    assert replaced.status_code == 200
    assert replaced.json()["published"] is True


def test_a_document_that_disagrees_with_the_path_is_refused(client: TestClient) -> None:
    """Two sources for one identity. Anything but a refusal can rename or overwrite."""
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    confused = client.put(
        "/api/v1/admin/waves/demo_first_steps",
        content=a_document("something_else"),
        headers=admin(client),
    )
    assert confused.status_code == 422


def test_a_document_that_is_not_a_wave_is_refused_with_the_field(client: TestClient) -> None:
    broken = json.loads(a_document())
    del broken["spawn_rules"]
    refused = client.post(
        "/api/v1/admin/waves", content=json.dumps(broken).encode(), headers=admin(client)
    )
    assert refused.status_code == 422
    assert "spawn_rules" in refused.json()["detail"]


def test_a_body_that_is_not_json_is_a_400_not_a_422(client: TestClient) -> None:
    """Could not be read, rather than read and unacceptable. An author debugs them differently."""
    refused = client.post("/api/v1/admin/waves", content=b"{nope", headers=admin(client))
    assert refused.status_code == 400


def test_two_waves_cannot_claim_the_same_position(client: TestClient) -> None:
    client.post("/api/v1/admin/waves", content=a_document("first", order=4), headers=admin(client))
    clash = client.post(
        "/api/v1/admin/waves", content=a_document("second", order=4), headers=admin(client)
    )
    assert clash.status_code == 422
    assert "/progression_config/order" in clash.json()["detail"], "say which field to change"


def test_next_order_is_one_past_the_last(client: TestClient) -> None:
    """A bare integer, as the frozen contract types `nextWaveOrder` and the Java answered."""
    assert client.get("/api/v1/admin/waves/next-order", headers=admin(client)).json() == 0
    client.post("/api/v1/admin/waves", content=a_document("first", order=7), headers=admin(client))
    assert client.get("/api/v1/admin/waves/next-order", headers=admin(client)).json() == 8


def test_a_wave_can_be_deleted(client: TestClient) -> None:
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    assert (
        client.delete("/api/v1/admin/waves/demo_first_steps", headers=admin(client)).status_code
        == 204
    )
    assert (
        client.get("/api/v1/admin/waves/demo_first_steps", headers=admin(client)).status_code == 404
    )


def test_deleting_a_wave_that_is_not_there_is_a_404(client: TestClient) -> None:
    assert client.delete("/api/v1/admin/waves/ghost", headers=admin(client)).status_code == 404


# --- publishing, and what a client sees -------------------------------------------------------


def test_publishing_puts_a_wave_in_front_of_clients(client: TestClient) -> None:
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    assert client.get("/api/v1/public/waves").json() == []

    client.post("/api/v1/admin/waves/demo_first_steps/publish", headers=admin(client))
    assert [w["id"] for w in client.get("/api/v1/public/waves").json()] == ["demo_first_steps"]


def test_publishing_moves_the_content_hash(client: TestClient) -> None:
    """Or a client that polls would never learn there is something new."""
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    before = client.get("/api/v1/public/status").json()["contentHash"]
    client.post("/api/v1/admin/waves/demo_first_steps/publish", headers=admin(client))
    assert client.get("/api/v1/public/status").json()["contentHash"] != before


def test_unpublishing_takes_it_back(client: TestClient) -> None:
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    client.post("/api/v1/admin/waves/demo_first_steps/publish", headers=admin(client))
    client.post("/api/v1/admin/waves/demo_first_steps/unpublish", headers=admin(client))

    assert client.get("/api/v1/public/waves").json() == []
    assert client.get("/api/v1/public/waves/demo_first_steps").status_code == 404


def test_publishing_something_that_is_not_there_is_a_404(client: TestClient) -> None:
    assert (
        client.post("/api/v1/admin/waves/ghost/publish", headers=admin(client)).status_code == 404
    )


def test_a_saved_wave_keeps_its_etag_when_nothing_changed(client: TestClient) -> None:
    """An author opening a wave and saving it unchanged must not expire every client's cache."""
    client.post("/api/v1/admin/waves", content=a_document(), headers=admin(client))
    client.post("/api/v1/admin/waves/demo_first_steps/publish", headers=admin(client))
    before = client.get("/api/v1/public/waves/demo_first_steps/raw").headers["etag"]

    client.put("/api/v1/admin/waves/demo_first_steps", content=a_document(), headers=admin(client))
    after = client.get("/api/v1/public/waves/demo_first_steps/raw").headers["etag"]
    assert after == before


# --- bulk import ------------------------------------------------------------------------------


def _batch(*documents: bytes) -> bytes:
    """Joined the way the project's import script joins them: verbatim, with commas."""
    return b"[" + b",".join(documents) + b"]"


def test_a_batch_imports_every_document_as_a_draft(client: TestClient) -> None:
    body = _batch(a_document("first", order=0), a_document("second", order=1))
    imported = client.post("/api/v1/admin/waves/bulk", content=body, headers=admin(client))

    assert imported.status_code == 200, imported.text
    assert [wave["id"] for wave in imported.json()] == ["first", "second"]
    assert all(wave["published"] is False for wave in imported.json())


def test_a_batch_keeps_each_document_byte_for_byte(client: TestClient) -> None:
    """The array is split rather than parsed. Re-serialising the elements would move the ETag
    of every wave in the batch."""
    first, second = a_document("first", order=0), a_document("second", order=1)
    client.post("/api/v1/admin/waves/bulk", content=_batch(first, second), headers=admin(client))

    assert client.get("/api/v1/admin/waves/first", headers=admin(client)).content == first
    assert client.get("/api/v1/admin/waves/second", headers=admin(client)).content == second


def test_one_bad_document_rejects_the_whole_batch(client: TestClient) -> None:
    """All or nothing. Half a catalogue is worse than none: nobody can tell which half arrived
    without reading the whole thing."""
    broken = json.loads(a_document("second", order=1))
    del broken["spawn_rules"]
    body = _batch(a_document("first", order=0), json.dumps(broken).encode())

    refused = client.post("/api/v1/admin/waves/bulk", content=body, headers=admin(client))
    assert refused.status_code == 422
    assert client.get("/api/v1/admin/waves", headers=admin(client)).json() == []


def test_a_rejection_names_the_document_by_position(client: TestClient) -> None:
    broken = json.loads(a_document("third", order=2))
    del broken["spawn_rules"]
    body = _batch(
        a_document("first", order=0), a_document("second", order=1), json.dumps(broken).encode()
    )
    refused = client.post("/api/v1/admin/waves/bulk", content=body, headers=admin(client))
    assert refused.json()["detail"].startswith("/2"), "the third document, counting from zero"


def test_two_documents_in_one_batch_cannot_claim_the_same_position(client: TestClient) -> None:
    body = _batch(a_document("first", order=5), a_document("second", order=5))
    refused = client.post("/api/v1/admin/waves/bulk", content=body, headers=admin(client))
    assert refused.status_code == 422
    assert client.get("/api/v1/admin/waves", headers=admin(client)).json() == []


def test_a_batch_that_is_not_an_array_is_a_400(client: TestClient) -> None:
    refused = client.post(
        "/api/v1/admin/waves/bulk", content=a_document(), headers=admin(client)
    )
    assert refused.status_code == 400


def test_importing_is_closed_to_a_viewer(client: TestClient) -> None:
    refused = client.post(
        "/api/v1/admin/waves/bulk", content=_batch(a_document()), headers=admin(client, VIEWER)
    )
    assert refused.status_code == 403
