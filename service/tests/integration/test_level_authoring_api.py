"""R2c: making, changing and deleting levels through the API, and deleting waves in a batch.

Before this, a level could only be made with SQL. Every rule here is one the database already
keeps — a membership row names a wave of the same project, one position holds one wave, one
level is active — and what these tests pin is that a route answers an author with the field to
change rather than letting a constraint violation through as a 500.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.players import EDITOR, VIEWER, account, serving
from wavemaker.apps.content.adapters.postgres import PostgresWaveRepository
from wavemaker.apps.content.domain.document import WaveDocument
from wavemaker.platform.tenancy import ensure_project

LEVELS = "/api/v1/admin/wave-levels"
BATCH_DELETE = "/api/v1/admin/waves/batch-delete"


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def a_wave(wave_id: str, order: int) -> WaveDocument:
    return WaveDocument.read(
        json.dumps(
            {"id": wave_id, "name": wave_id.title(), "progression_config": {"order": order}}
        ).encode()
    )


def seed(client: TestClient, *wave_ids: str, published: tuple[str, ...] = ()) -> None:
    """Waves stored straight through the repository: these tests are about levels, and the
    wave routes have tests of their own."""
    app: Any = client.app
    with app.state.session_factory() as session:
        store = PostgresWaveRepository(session, app.state.project_id)
        for order, wave_id in enumerate(wave_ids):
            store.save(a_wave(wave_id, order))
        for wave_id in published:
            store.set_published(wave_id, True)


def wave_ids(client: TestClient) -> list[str]:
    listed = client.get("/api/v1/admin/waves", headers=account(client)).json()
    return [wave["id"] for wave in listed]


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    payload = {"name": "Act One", "waves": []} | body
    response = client.post(LEVELS, json=payload, headers=account(client))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def members(level: dict[str, Any]) -> list[str]:
    return [member["waveId"] for member in level["waves"]]


# --- AC-1: a level names waves in order, drafts included ---------------------------------------


@pytest.mark.ac("AC-1")
def test_a_level_is_created_with_its_waves_in_order_drafts_included(client: TestClient) -> None:
    seed(client, "first", "second", "draft", published=("first", "second"))

    created = create(
        client, name="Act One", description="Opening", waves=["second", "draft", "first"]
    )

    assert created["name"] == "Act One"
    assert created["description"] == "Opening"
    assert created["waves"] == [
        {"waveId": "second", "published": True},
        {"waveId": "draft", "published": False},
        {"waveId": "first", "published": True},
    ]
    uuid.UUID(created["id"])  # the engine assigns the id, and it is a real one
    assert created["createdAt"].endswith("Z") and created["updatedAt"].endswith("Z")


@pytest.mark.ac("AC-1")
def test_creating_a_level_never_activates_it(client: TestClient) -> None:
    seed(client, "first", published=("first",))
    assert create(client, waves=["first"])["active"] is False
    assert client.get("/api/v1/public/wave-levels/active").status_code == 404


@pytest.mark.ac("AC-1")
def test_a_level_reads_back_by_id_and_in_the_list(client: TestClient) -> None:
    seed(client, "first", "draft", published=("first",))
    created = create(client, waves=["draft", "first"])

    fetched = client.get(f"{LEVELS}/{created['id']}", headers=account(client))
    assert fetched.status_code == 200
    assert fetched.json() == created

    listed = client.get(LEVELS, headers=account(client)).json()
    assert listed == [created]


@pytest.mark.ac("AC-1")
def test_publishing_a_member_shows_in_the_level(client: TestClient) -> None:
    """The member's state is read when the level is read, not copied when it was made."""
    seed(client, "draft")
    created = create(client, waves=["draft"])
    client.post("/api/v1/admin/waves/draft/publish", headers=account(client))

    fetched = client.get(f"{LEVELS}/{created['id']}", headers=account(client)).json()
    assert fetched["waves"] == [{"waveId": "draft", "published": True}]


@pytest.mark.ac("AC-1")
def test_a_level_with_no_waves_is_a_level(client: TestClient) -> None:
    created = create(client, waves=[])
    assert created["waves"] == []
    assert created["description"] is None


@pytest.mark.ac("AC-1")
def test_a_level_without_a_name_is_refused_naming_the_field(client: TestClient) -> None:
    refused = client.post(LEVELS, json={"name": "  ", "waves": []}, headers=account(client))
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("/name")


@pytest.mark.ac("AC-1")
def test_a_body_that_is_not_json_is_a_400(client: TestClient) -> None:
    refused = client.post(LEVELS, content=b"{nope", headers=account(client))
    assert refused.status_code == 400


@pytest.mark.ac("AC-1")
def test_a_level_without_a_wave_list_is_refused(client: TestClient) -> None:
    """Absent is not empty: a client that forgot the field must not get an empty level."""
    refused = client.post(LEVELS, json={"name": "Act One"}, headers=account(client))
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("/waves")


# --- AC-2: one position, one wave; one wave, one position ---------------------------------------


@pytest.mark.ac("AC-2")
def test_a_level_cannot_list_a_wave_twice(client: TestClient) -> None:
    seed(client, "first", "second")
    refused = client.post(
        LEVELS,
        json={"name": "Act One", "waves": ["first", "second", "first"]},
        headers=account(client),
    )
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("/waves/2")
    assert client.get(LEVELS, headers=account(client)).json() == [], "nothing was stored"


@pytest.mark.ac("AC-2")
def test_an_update_cannot_list_a_wave_twice_either(client: TestClient) -> None:
    seed(client, "first", "second")
    created = create(client, waves=["first", "second"])
    refused = client.put(
        f"{LEVELS}/{created['id']}",
        json={"name": "Act One", "waves": ["second", "second"]},
        headers=account(client),
    )
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("/waves/1")


# --- AC-3: only waves of this project --------------------------------------------------------


@pytest.mark.ac("AC-3")
def test_a_wave_that_does_not_exist_is_refused_naming_its_position(client: TestClient) -> None:
    seed(client, "first")
    refused = client.post(
        LEVELS,
        json={"name": "Act One", "waves": ["first", "ghost", "phantom"]},
        headers=account(client),
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "/waves/1" in detail and "ghost" in detail
    assert "/waves/2" in detail and "phantom" in detail, "every missing wave, not the first"
    assert client.get(LEVELS, headers=account(client)).json() == []


@pytest.mark.ac("AC-3")
def test_a_wave_from_another_project_is_not_a_wave_of_this_one(client: TestClient) -> None:
    """The composite foreign key makes this impossible to store. The route must say so as a
    422 rather than let the violation out as a 500, and must not find the wave either."""
    app: Any = client.app
    with app.state.session_factory() as session:
        elsewhere = ensure_project(session, "elsewhere", "Elsewhere")
        PostgresWaveRepository(session, elsewhere).save(a_wave("foreign", 0))

    refused = client.post(
        LEVELS, json={"name": "Act One", "waves": ["foreign"]}, headers=account(client)
    )
    assert refused.status_code == 422
    assert "/waves/0" in refused.json()["detail"]


@pytest.mark.ac("AC-3")
def test_an_id_too_long_to_be_a_wave_is_a_missing_wave_not_a_500(client: TestClient) -> None:
    refused = client.post(
        LEVELS, json={"name": "Act One", "waves": ["x" * 300]}, headers=account(client)
    )
    assert refused.status_code == 422
    assert "/waves/0" in refused.json()["detail"]


# --- AC-4: replacing a level is all or nothing ----------------------------------------------


@pytest.mark.ac("AC-4")
def test_an_update_renames_and_resequences_a_level(client: TestClient) -> None:
    seed(client, "first", "second", "third", published=("second",))
    created = create(client, name="Act One", description="Opening", waves=["first", "second"])

    updated = client.put(
        f"{LEVELS}/{created['id']}",
        json={"name": "Act Two", "waves": ["third", "second", "first"]},
        headers=account(client),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["id"] == created["id"]
    assert body["name"] == "Act Two"
    assert body["description"] is None, "the request replaces the level; absent is cleared"
    assert body["waves"] == [
        {"waveId": "third", "published": False},
        {"waveId": "second", "published": True},
        {"waveId": "first", "published": False},
    ]
    assert body["createdAt"] == created["createdAt"]
    assert datetime.fromisoformat(body["updatedAt"]) >= datetime.fromisoformat(created["updatedAt"])


@pytest.mark.ac("AC-4")
def test_reversing_a_level_does_not_collide_with_itself(client: TestClient) -> None:
    """Every wave moves to a position another wave holds. Rewriting rows in place collides
    with the unique position halfway through, which is what broke the Java's first try."""
    seed(client, "a", "b", "c", "d")
    created = create(client, waves=["a", "b", "c", "d"])
    updated = client.put(
        f"{LEVELS}/{created['id']}",
        json={"name": "Act One", "waves": ["d", "c", "b", "a"]},
        headers=account(client),
    )
    assert updated.status_code == 200, updated.text
    assert members(updated.json()) == ["d", "c", "b", "a"]


@pytest.mark.ac("AC-4")
def test_a_refused_update_leaves_the_old_level_whole(client: TestClient) -> None:
    seed(client, "first", "second")
    created = create(client, name="Act One", waves=["first", "second"])

    refused = client.put(
        f"{LEVELS}/{created['id']}",
        json={"name": "Renamed", "waves": ["second", "ghost"]},
        headers=account(client),
    )
    assert refused.status_code == 422

    after = client.get(f"{LEVELS}/{created['id']}", headers=account(client)).json()
    assert after == created, "not renamed, not resequenced, not emptied"


@pytest.mark.ac("AC-4")
def test_an_active_level_stays_active_when_it_is_updated(client: TestClient) -> None:
    seed(client, "first", "second", published=("first", "second"))
    created = create(client, waves=["first"])
    client.post(f"{LEVELS}/{created['id']}/activate", headers=account(client))

    client.put(
        f"{LEVELS}/{created['id']}",
        json={"name": "Act One", "waves": ["second", "first"]},
        headers=account(client),
    )
    served = client.get("/api/v1/public/wave-levels/active").json()
    assert [wave["id"] for wave in served["waves"]] == ["second", "first"]


# --- AC-5: deleting a level -------------------------------------------------------------------


@pytest.mark.ac("AC-5")
def test_deleting_a_level_leaves_its_waves(client: TestClient) -> None:
    seed(client, "first", "draft", published=("first",))
    created = create(client, waves=["first", "draft"])

    deleted = client.delete(f"{LEVELS}/{created['id']}", headers=account(client))
    assert deleted.status_code == 204

    assert client.get(f"{LEVELS}/{created['id']}", headers=account(client)).status_code == 404
    assert wave_ids(client) == ["first", "draft"]
    assert [w["id"] for w in client.get("/api/v1/public/waves").json()] == ["first"]


@pytest.mark.ac("AC-5")
def test_deleting_the_active_level_leaves_none_active(client: TestClient) -> None:
    seed(client, "first", published=("first",))
    active = create(client, name="Act One", waves=["first"])
    other = create(client, name="Act Two", waves=["first"])
    client.post(f"{LEVELS}/{active['id']}/activate", headers=account(client))

    client.delete(f"{LEVELS}/{active['id']}", headers=account(client))

    assert client.get("/api/v1/public/wave-levels/active").status_code == 404
    remaining = client.get(LEVELS, headers=account(client)).json()
    assert [(level["id"], level["active"]) for level in remaining] == [(other["id"], False)]


@pytest.mark.ac("AC-5")
def test_deleting_a_level_takes_its_membership_rows_with_it(client: TestClient) -> None:
    seed(client, "first")
    created = create(client, waves=["first"])
    client.delete(f"{LEVELS}/{created['id']}", headers=account(client))

    app: Any = client.app
    with app.state.session_factory() as session:
        left = session.execute(text("select count(*) from wave_level_wave")).scalar_one()
    assert left == 0


# --- AC-6: batch delete is all or nothing ------------------------------------------------------


@pytest.mark.ac("AC-6")
def test_a_batch_delete_removes_every_wave_named(client: TestClient) -> None:
    seed(client, "first", "second", "third")
    deleted = client.post(BATCH_DELETE, json={"ids": ["third", "first"]}, headers=account(client))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": 2}
    assert wave_ids(client) == ["second"]


@pytest.mark.ac("AC-6")
def test_one_unknown_id_deletes_nothing_and_is_named(client: TestClient) -> None:
    seed(client, "first", "second")
    refused = client.post(
        BATCH_DELETE, json={"ids": ["first", "ghost", "second"]}, headers=account(client)
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "/ids/1" in detail and "ghost" in detail
    assert wave_ids(client) == ["first", "second"], "not even the ones that were there"


@pytest.mark.ac("AC-6")
def test_a_batch_delete_takes_the_waves_out_of_their_levels(client: TestClient) -> None:
    seed(client, "first", "second")
    created = create(client, waves=["first", "second"])
    client.post(BATCH_DELETE, json={"ids": ["first"]}, headers=account(client))

    level = client.get(f"{LEVELS}/{created['id']}", headers=account(client)).json()
    assert members(level) == ["second"]


@pytest.mark.ac("AC-6")
def test_a_wave_of_another_project_cannot_be_batch_deleted(client: TestClient) -> None:
    app: Any = client.app
    with app.state.session_factory() as session:
        elsewhere = ensure_project(session, "elsewhere", "Elsewhere")
        PostgresWaveRepository(session, elsewhere).save(a_wave("foreign", 0))

    refused = client.post(BATCH_DELETE, json={"ids": ["foreign"]}, headers=account(client))
    assert refused.status_code == 422

    with app.state.session_factory() as session:
        assert PostgresWaveRepository(session, elsewhere).document("foreign") is not None


@pytest.mark.ac("AC-6")
@pytest.mark.parametrize("body", [{"ids": []}, {"ids": ["a", "a"]}, {}, {"ids": "a"}])
def test_a_batch_that_is_not_a_known_set_is_a_422(client: TestClient, body: Any) -> None:
    seed(client, "a")
    answer = client.post(BATCH_DELETE, json=body, headers=account(client))
    assert answer.status_code == 422
    assert wave_ids(client) == ["a"]


@pytest.mark.ac("AC-6")
def test_a_batch_that_is_not_json_is_a_400(client: TestClient) -> None:
    refused = client.post(BATCH_DELETE, content=b"[nope", headers=account(client))
    assert refused.status_code == 400


# --- AC-7: unknown and malformed level ids ------------------------------------------------------


UNKNOWN = str(uuid.uuid4())


@pytest.mark.ac("AC-7")
@pytest.mark.parametrize("level_id", [UNKNOWN, "not-a-uuid", "1"])
def test_an_unknown_or_malformed_level_is_a_404_on_every_route(
    client: TestClient, level_id: str
) -> None:
    """A malformed id is the same answer as one that is not there. Telling them apart says
    which ids are shaped correctly, and nobody can act on that."""
    headers = account(client)
    body = {"name": "Act One", "waves": []}
    assert client.get(f"{LEVELS}/{level_id}", headers=headers).status_code == 404
    answer = client.put(f"{LEVELS}/{level_id}", json=body, headers=headers)
    assert answer.status_code == 404
    answer = client.delete(f"{LEVELS}/{level_id}", headers=headers)
    assert answer.status_code == 404
    answer = client.post(f"{LEVELS}/{level_id}/activate", headers=headers)
    assert answer.status_code == 404


@pytest.mark.ac("AC-7")
def test_an_update_to_a_level_that_is_not_there_creates_nothing(client: TestClient) -> None:
    client.put(f"{LEVELS}/{UNKNOWN}", json={"name": "Ghost", "waves": []}, headers=account(client))
    assert client.get(LEVELS, headers=account(client)).json() == []


# --- AC-8: who may change levels ---------------------------------------------------------------


@pytest.mark.ac("AC-8")
def test_level_authoring_is_closed_without_a_token(client: TestClient) -> None:
    answer = client.post(LEVELS, json={"name": "x", "waves": []})
    assert answer.status_code == 401
    assert client.get(f"{LEVELS}/{UNKNOWN}").status_code == 401
    answer = client.put(f"{LEVELS}/{UNKNOWN}", json={"name": "x", "waves": []})
    assert answer.status_code == 401
    answer = client.delete(f"{LEVELS}/{UNKNOWN}")
    assert answer.status_code == 401
    answer = client.post(BATCH_DELETE, json={"ids": ["a"]})
    assert answer.status_code == 401


@pytest.mark.ac("AC-8")
def test_a_viewer_may_read_a_level_but_not_change_it(client: TestClient) -> None:
    seed(client, "first")
    created = create(client, waves=["first"])
    viewer = account(client, VIEWER)

    assert client.get(f"{LEVELS}/{created['id']}", headers=viewer).status_code == 200
    body = {"name": "Mine now", "waves": []}
    answer = client.post(LEVELS, json=body, headers=viewer)
    assert answer.status_code == 403
    answer = client.put(f"{LEVELS}/{created['id']}", json=body, headers=viewer)
    assert answer.status_code == 403
    answer = client.delete(f"{LEVELS}/{created['id']}", headers=viewer)
    assert answer.status_code == 403
    answer = client.post(BATCH_DELETE, json={"ids": ["first"]}, headers=viewer)
    assert answer.status_code == 403
    assert wave_ids(client) == ["first"]


@pytest.mark.ac("AC-8")
def test_an_editor_may_author_levels(client: TestClient) -> None:
    seed(client, "first")
    editor = account(client, EDITOR)
    created = client.post(LEVELS, json={"name": "Act One", "waves": ["first"]}, headers=editor)
    assert created.status_code == 201
    level_id = created.json()["id"]
    renamed = client.put(
        f"{LEVELS}/{level_id}", json={"name": "Act Two", "waves": []}, headers=editor
    )
    assert renamed.status_code == 200
    answer = client.delete(f"{LEVELS}/{level_id}", headers=editor)
    assert answer.status_code == 204
    answer = client.post(BATCH_DELETE, json={"ids": ["first"]}, headers=editor)
    assert answer.status_code == 200


# --- the frozen contract ----------------------------------------------------------------------

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi-v1.json"
OPERATIONS = [
    ("post", "/api/v1/admin/wave-levels", "createWaveLevel"),
    ("get", "/api/v1/admin/wave-levels/{id}", "getWaveLevel"),
    ("put", "/api/v1/admin/wave-levels/{id}", "updateWaveLevel"),
    ("delete", "/api/v1/admin/wave-levels/{id}", "deleteWaveLevel"),
    ("post", "/api/v1/admin/waves/batch-delete", "batchDeleteWaves"),
]


def contract() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(CONTRACT.read_text())
    return document


def fields_of(schema: str) -> set[str]:
    return set(contract()["components"]["schemas"][schema]["properties"])


@pytest.mark.ac("AC-1")
@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS)
def test_each_route_is_served_where_the_contract_puts_it(
    client: TestClient, method: str, path: str, operation: str
) -> None:
    """The path and the operation id, both: generated clients name their methods after the
    second, so a route at the right path under another name is a client that will not build."""
    assert contract()["paths"][path][method]["operationId"] == operation
    served = client.get("/openapi.json").json()["paths"]
    by_id = {
        details["operationId"]: (verb, route)
        for route, verbs in served.items()
        for verb, details in verbs.items()
    }
    assert by_id.get(operation) == (method, path)


@pytest.mark.ac("AC-1")
def test_every_body_spells_its_fields_the_way_the_contract_does(client: TestClient) -> None:
    seed(client, "first", "second")
    created = create(client, description="Opening", waves=["first"])
    deleted = client.post(BATCH_DELETE, json={"ids": ["second"]}, headers=account(client)).json()

    assert set(created) == fields_of("WaveLevelSummary")
    assert set(created["waves"][0]) == fields_of("WaveLevelMember")
    assert set(deleted) == fields_of("WaveBatchDeleteResult")
    assert fields_of("WaveLevelRequest") == {"name", "description", "waves"}
    assert fields_of("WaveBatchDeleteRequest") == {"ids"}
