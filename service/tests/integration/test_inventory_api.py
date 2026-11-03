"""The inventory over HTTP: an editor's catalogue and grants, and a player's own view.

Every shape here is the frozen v1 contract's: `ItemView`, `ItemRequest`, `PlayerInventory`,
`InventoryGrantRequest`, at the paths and with the operation ids it names. The last test reads
the contract file and checks the service answers each inventory operation where it says.
"""

from __future__ import annotations

import json
import socket
import urllib.request
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.integration.players import (
    ADMIN,
    EDITOR,
    VIEWER,
    account,
    mint_key,
    player,
    serving,
    tokens,
)

CONTRACT = Path(__file__).resolve().parents[3] / "docs/api/openapi-v1.json"

SWORD = {"name": "Sword", "itemType": "weapon", "spriteRef": "sprites/sword", "attributes": "{}"}

DAMAGE_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": ["damage"],
        "properties": {
            "damage": {"type": "integer", "minimum": 1},
            "element": {"enum": ["fire", "ice"]},
            "stats": {"type": "object", "properties": {"speed": {"type": "number"}}},
        },
        "additionalProperties": False,
    }
)


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def put_item(client: TestClient, item_id: str, body: Any = None, email: str = EDITOR) -> Any:
    return client.put(
        f"/api/v1/admin/items/{item_id}",
        json=SWORD if body is None else body,
        headers=account(client, email),
    )


def put_schema(client: TestClient, schema: str | bytes, email: str = EDITOR) -> Any:
    return client.put(
        "/api/v1/admin/item-schema",
        content=schema.encode() if isinstance(schema, str) else schema,
        headers={**account(client, email), "Content-Type": "application/json"},
    )


def give(client: TestClient, player_id: str, *lines: tuple[str, Any], email: str = EDITOR) -> Any:
    return client.post(
        f"/api/v1/admin/players/{player_id}/inventory/grant",
        json={"items": [{"itemId": item, "quantity": quantity} for item, quantity in lines]},
        headers=account(client, email),
    )


def held(client: TestClient, headers: dict[str, str]) -> dict[str, int]:
    response = client.get("/api/v1/player/me/inventory", headers=headers)
    assert response.status_code == 200, response.text
    return {entry["itemId"]: entry["quantity"] for entry in response.json()["items"]}


def detail(response: Any) -> str:
    message: str = response.json()["detail"]
    return message


# --- AC-1: the catalogue is an editor's ----------------------------------------------------------


@pytest.mark.parametrize("email", [EDITOR, ADMIN])
def test_ac1_an_editor_defines_an_item_and_reads_it_back(client: TestClient, email: str) -> None:
    saved = put_item(client, "sword", email=email)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert {k: body[k] for k in ("id", "name", "itemType", "spriteRef", "attributes")} == {
        "id": "sword",
        "name": "Sword",
        "itemType": "weapon",
        "spriteRef": "sprites/sword",
        "attributes": "{}",
    }
    assert body["createdAt"].endswith("Z")
    assert body["updatedAt"].endswith("Z")

    assert client.get("/api/v1/admin/items/sword", headers=account(client)).json() == body
    listed = client.get("/api/v1/admin/items", headers=account(client))
    assert listed.status_code == 200
    assert listed.json() == [body]


def test_ac1_a_put_replaces_and_keeps_the_creation_time(client: TestClient) -> None:
    first = put_item(client, "sword").json()
    second = put_item(
        client, "sword", {"name": "Great Sword", "itemType": "two_handed", "attributes": "{}"}
    ).json()

    assert second["name"] == "Great Sword"
    assert second["itemType"] == "two_handed"
    assert second["spriteRef"] is None, "a replacement replaces every field, sprite included"
    assert second["createdAt"] == first["createdAt"]
    assert second["updatedAt"] >= first["updatedAt"]
    assert len(client.get("/api/v1/admin/items", headers=account(client)).json()) == 1


def test_ac1_items_are_listed_by_id(client: TestClient) -> None:
    for item_id in ("shield", "arrow", "sword"):
        put_item(client, item_id)
    listed = client.get("/api/v1/admin/items", headers=account(client)).json()
    assert [item["id"] for item in listed] == ["arrow", "shield", "sword"]


def test_ac1_an_item_is_deleted_with_a_204_and_is_then_gone(client: TestClient) -> None:
    put_item(client, "sword")
    deleted = client.delete("/api/v1/admin/items/sword", headers=account(client))
    assert deleted.status_code == 204
    assert client.get("/api/v1/admin/items/sword", headers=account(client)).status_code == 404
    assert client.delete("/api/v1/admin/items/sword", headers=account(client)).status_code == 404


@pytest.mark.parametrize("item_id", ["nothing_here", "Not-An-Id", "x" * 65])
def test_ac1_an_unknown_or_malformed_id_is_not_found(client: TestClient, item_id: str) -> None:
    assert client.get(f"/api/v1/admin/items/{item_id}", headers=account(client)).status_code == 404
    deleted = client.delete(f"/api/v1/admin/items/{item_id}", headers=account(client))
    assert deleted.status_code == 404


def test_ac1_saving_under_a_malformed_id_names_the_id(client: TestClient) -> None:
    response = put_item(client, "Sword")
    assert response.status_code == 422
    assert detail(response).startswith("/id:")


def test_ac1_an_item_called_schema_is_an_item(client: TestClient) -> None:
    """Why the schema lives at /item-schema: under /items it would shadow this one."""
    assert put_item(client, "schema").status_code == 200
    item = client.get("/api/v1/admin/items/schema", headers=account(client))
    assert item.json()["id"] == "schema"


ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/items"),
    ("GET", "/api/v1/admin/items/sword"),
    ("PUT", "/api/v1/admin/items/sword"),
    ("DELETE", "/api/v1/admin/items/sword"),
    ("GET", "/api/v1/admin/item-schema"),
    ("PUT", "/api/v1/admin/item-schema"),
    ("GET", "/api/v1/admin/players/{player}/inventory"),
    ("POST", "/api/v1/admin/players/{player}/inventory/grant"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_ac1_a_viewer_may_not_look_or_change_anything(
    client: TestClient, method: str, path: str
) -> None:
    """As in the Java's authorisation matrix: items are content an editor defines, and a
    viewer was refused even the list."""
    put_item(client, "sword")
    _, player_id = player(client)
    response = client.request(
        method,
        path.format(player=player_id),
        json={**SWORD, "items": [{"itemId": "sword", "quantity": 1}]},
        headers=account(client, VIEWER),
    )
    assert response.status_code == 403


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_ac1_nobody_unsigned_reaches_the_catalogue(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path.format(player=uuid.uuid4()), json=SWORD)
    assert response.status_code == 401


# --- AC-2: attributes, verbatim ------------------------------------------------------------------


def test_ac2_attributes_come_back_as_the_exact_text_that_was_sent(client: TestClient) -> None:
    sent = '{ "damage": 12.0,\n  "b": 1, "a": [1, 2.50] }'
    saved = put_item(client, "sword", {**SWORD, "attributes": sent})
    assert saved.json()["attributes"] == sent
    read = client.get("/api/v1/admin/items/sword", headers=account(client))
    assert read.json()["attributes"] == sent


def test_ac2_no_attributes_is_an_empty_document(client: TestClient) -> None:
    saved = put_item(client, "sword", {"name": "Sword", "itemType": "weapon"})
    assert saved.status_code == 200
    assert saved.json()["attributes"] == "{}"


@pytest.mark.parametrize("attributes", [{"damage": 12}, [1, 2], 12, "[1, 2]", "12", "{broken"])
def test_ac2_attributes_are_a_json_object_inside_a_string(
    client: TestClient, attributes: Any
) -> None:
    response = put_item(client, "sword", {**SWORD, "attributes": attributes})
    assert response.status_code == 422
    assert detail(response).startswith("/attributes:")


# --- AC-3: validated against the project's own schema ---------------------------------------------


def test_ac3_with_no_schema_any_object_is_accepted(client: TestClient) -> None:
    attributes = '{"whatever": {"the": ["project", "likes"]}}'
    assert put_item(client, "sword", {**SWORD, "attributes": attributes}).status_code == 200


def test_ac3_attributes_that_satisfy_the_schema_are_saved(client: TestClient) -> None:
    assert put_schema(client, DAMAGE_SCHEMA).status_code == 200
    attributes = '{"damage": 12, "element": "fire", "stats": {"speed": 1.5}}'
    saved = put_item(client, "sword", {**SWORD, "attributes": attributes})
    assert saved.status_code == 200, saved.text
    assert saved.json()["attributes"] == attributes


def test_ac3_violations_are_reported_at_attributes_plus_the_pointer_inside(
    client: TestClient,
) -> None:
    """The caller sent a whole item, so `/damage` would name a field their request does not
    have at the top level."""
    put_schema(client, DAMAGE_SCHEMA)
    response = put_item(
        client, "sword", {**SWORD, "attributes": '{"damage": 12, "stats": {"speed": "fast"}}'}
    )
    assert response.status_code == 422
    assert detail(response).startswith("/attributes/stats/speed:")


def test_ac3_every_violation_is_reported_in_pointer_order(client: TestClient) -> None:
    put_schema(client, DAMAGE_SCHEMA)
    response = put_item(
        client, "sword", {**SWORD, "attributes": '{"element": "mud", "damage": 0, "extra": 1}'}
    )
    assert response.status_code == 422
    problems = detail(response).split("; ")
    assert [problem.split(":")[0] for problem in problems] == [
        "/attributes",
        "/attributes/damage",
        "/attributes/element",
    ], problems
    assert "Additional properties" in problems[0]


def test_ac3_a_refused_item_is_not_stored(client: TestClient) -> None:
    put_schema(client, DAMAGE_SCHEMA)
    put_item(client, "sword", {**SWORD, "attributes": '{"damage": 0}'})
    assert client.get("/api/v1/admin/items/sword", headers=account(client)).status_code == 404


def test_ac3_tightening_the_schema_does_not_revalidate_existing_items(client: TestClient) -> None:
    """Otherwise half a catalogue becomes unsaveable with nothing saying which half."""
    put_item(client, "sword", {**SWORD, "attributes": '{"weight": 3}'})
    assert put_schema(client, DAMAGE_SCHEMA).status_code == 200
    read = client.get("/api/v1/admin/items/sword", headers=account(client))
    assert read.status_code == 200
    assert read.json()["attributes"] == '{"weight": 3}'
    # It is checked on its next save.
    assert put_item(client, "sword", {**SWORD, "attributes": '{"weight": 3}'}).status_code == 422


def test_ac3_false_refuses_every_item_and_an_empty_schema_none(client: TestClient) -> None:
    put_schema(client, "false")
    assert put_item(client, "sword").status_code == 422
    put_schema(client, "{}")
    assert put_item(client, "sword").status_code == 200


def test_ac3_a_deep_document_against_a_recursive_schema_is_answered(client: TestClient) -> None:
    """At the depth limit, through a self-referencing schema, in a server thread: an answer,
    not a stack overflow."""
    put_schema(client, '{"type": "object", "additionalProperties": {"anyOf": [{"$ref": "#"}]}}')
    nested = '{"a": ' * 63 + "{}" + "}" * 63
    assert put_item(client, "sword", {**SWORD, "attributes": nested}).status_code == 200


# --- AC-4: the schema itself ---------------------------------------------------------------------


def test_ac4_with_no_schema_set_the_answer_is_an_empty_object(client: TestClient) -> None:
    response = client.get("/api/v1/admin/item-schema", headers=account(client))
    assert response.status_code == 200
    assert response.text == "{}"
    assert response.headers["content-type"].startswith("application/json")


def test_ac4_the_schema_is_stored_and_served_as_the_text_it_was_set_as(client: TestClient) -> None:
    text_sent = '{\n  "type" : "object",\n  "properties": {"damage": {"minimum": 1.0}}\n}\n'
    saved = put_schema(client, text_sent)
    assert saved.status_code == 200
    assert saved.text == text_sent
    assert client.get("/api/v1/admin/item-schema", headers=account(client)).text == text_sent


@pytest.mark.parametrize("schema", ["[1, 2, 3]", "[]", "5", '"object"', "null"])
def test_ac4_a_schema_that_is_not_an_object_or_a_boolean_is_refused(
    client: TestClient, schema: str
) -> None:
    """The Java accepted the array: its library compiled it into a schema that validates
    nothing, and every item would have passed."""
    put_schema(client, DAMAGE_SCHEMA)
    response = put_schema(client, schema)
    assert response.status_code == 422
    assert "an item schema is a JSON object, or true or false" in detail(response)
    # Refused means not stored: the previous schema still holds, and still refuses.
    assert client.get("/api/v1/admin/item-schema", headers=account(client)).text == DAMAGE_SCHEMA
    assert put_item(client, "sword", {**SWORD, "attributes": "{}"}).status_code == 422


@pytest.mark.parametrize(
    ("schema", "where"),
    [
        ('{"type": "nope"}', "/type:"),
        ('{"properties": {"name": {"pattern": "["}}}', "/properties/name/pattern:"),
        ('{"properties": {"a": {"$ref": "#/$defs/missing"}}}', "the reference"),
        ('{"$schema": "http://json-schema.org/draft-07/schema#"}', "/$schema:"),
        ("{not json", "this is not JSON"),
        ("", "send a schema"),
    ],
)
def test_ac4_an_unusable_schema_is_refused_when_it_is_set(
    client: TestClient, schema: str, where: str
) -> None:
    response = put_schema(client, schema)
    assert response.status_code == 422
    assert where in detail(response)


def test_ac4_a_schema_past_the_limit_is_refused(client: TestClient) -> None:
    enormous = json.dumps({"type": "object", "description": "x" * (2 * 1024 * 1024)})
    response = put_schema(client, enormous)
    assert response.status_code == 422
    assert "at most" in detail(response)


# --- AC-5: never a fetch ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema",
    [
        '{"$ref": "https://attacker.example/schema.json"}',
        '{"properties": {"a": {"$ref": "http://169.254.169.254/latest/meta-data/"}}}',
        '{"\\u0024ref": "https://attacker.example/schema.json"}',
        '{"$defs": {"x": {"$dynamicRef": "file:///etc/passwd"}}}',
    ],
)
def test_ac5_a_remote_reference_is_refused(client: TestClient, schema: str) -> None:
    response = put_schema(client, schema)
    assert response.status_code == 422
    assert "local reference" in detail(response)
    assert client.get("/api/v1/admin/item-schema", headers=account(client)).text == "{}"


def test_ac5_a_local_reference_works(client: TestClient) -> None:
    schema = json.dumps(
        {
            "$defs": {"positive": {"type": "integer", "minimum": 1}},
            "properties": {"damage": {"$ref": "#/$defs/positive"}},
        }
    )
    assert put_schema(client, schema).status_code == 200
    assert put_item(client, "sword", {**SWORD, "attributes": '{"damage": 3}'}).status_code == 200
    refused = put_item(client, "sword", {**SWORD, "attributes": '{"damage": 0}'})
    assert detail(refused).startswith("/attributes/damage:")


def test_ac5_a_remote_schema_written_past_the_service_fetches_nothing(
    client: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first check is skipped entirely: the row is written straight to the table. Saving
    an item must still not reach the network, and must still be an answer, not a 500.

    The database is reached through libpq, beneath Python's socket module, so the tripwire
    sees only what Python code tries."""
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("""
                insert into inventory_item_schema (project_id, schema_json, updated_at)
                select id, :schema, now() from project
            """),
            {"schema": '{"$ref": "https://attacker.example/schema.json"}'},
        )
    engine.dispose()
    headers = account(client)

    attempts: list[str] = []

    def tripwire(*args: Any, **_: Any) -> Any:
        attempts.append(repr(args[:2]))
        raise OSError("this test does not allow the network")

    monkeypatch.setattr(urllib.request, "urlopen", tripwire)
    monkeypatch.setattr(socket, "create_connection", tripwire)
    monkeypatch.setattr(socket, "getaddrinfo", tripwire)

    response = client.put("/api/v1/admin/items/sword", json=SWORD, headers=headers)
    assert response.status_code == 422
    assert "this project's item schema cannot be used" in detail(response)
    assert attempts == []


# --- AC-6: grants, all or nothing ----------------------------------------------------------------


@pytest.fixture
def stocked(client: TestClient) -> TestClient:
    for item_id in ("sword", "shield", "arrow"):
        assert put_item(client, item_id).status_code == 200
    return client


def test_ac6_an_editor_grants_several_items_and_the_player_sees_them(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    granted = give(stocked, player_id, ("sword", 1), ("arrow", 20))
    assert granted.status_code == 200, granted.text
    entries = granted.json()["items"]
    assert [(e["itemId"], e["quantity"]) for e in entries] == [("arrow", 20), ("sword", 1)]
    assert all(entry["updatedAt"].endswith("Z") for entry in entries)
    assert held(stocked, headers) == {"arrow": 20, "sword": 1}


def test_ac6_the_answer_is_everything_the_player_then_holds(stocked: TestClient) -> None:
    """`PlayerInventory` is everything a player holds, from either route."""
    headers, player_id = player(stocked)
    give(stocked, player_id, ("sword", 1))
    after = give(stocked, player_id, ("arrow", 5)).json()
    assert after == stocked.get("/api/v1/player/me/inventory", headers=headers).json()
    assert {e["itemId"] for e in after["items"]} == {"sword", "arrow"}


def test_ac6_a_negative_quantity_takes_away_and_zero_is_kept(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    give(stocked, player_id, ("arrow", 3))
    assert give(stocked, player_id, ("arrow", -3)).status_code == 200
    assert held(stocked, headers) == {"arrow": 0}, "had three and used them is not never had any"


def test_ac6_taking_more_than_is_held_is_refused_and_nothing_moves(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    give(stocked, player_id, ("arrow", 2))
    response = give(stocked, player_id, ("sword", 1), ("arrow", -3))
    assert response.status_code == 422
    assert detail(response).startswith("/items/1/quantity:")
    assert held(stocked, headers) == {"arrow": 2}, "the sword of a refused grant was not given"


def test_ac6_taking_what_was_never_held_is_refused(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    response = give(stocked, player_id, ("shield", -1))
    assert response.status_code == 422
    assert detail(response).startswith("/items/0/quantity:")
    assert held(stocked, headers) == {}


def test_ac6_one_unknown_item_rolls_back_the_whole_grant(stocked: TestClient) -> None:
    """A player who received the sword and not the shield has been given something the game
    never offered, and the inventory would look perfectly consistent."""
    headers, player_id = player(stocked)
    response = give(stocked, player_id, ("sword", 1), ("dragon", 1), ("shield", 1), ("ghost", 2))
    assert response.status_code == 422
    assert detail(response) == (
        "/items/1/itemId: no item 'dragon' in this project; "
        "/items/3/itemId: no item 'ghost' in this project"
    )
    assert held(stocked, headers) == {}


def test_ac6_a_line_may_repeat_an_item_and_lines_apply_in_order(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    assert give(stocked, player_id, ("arrow", 5), ("arrow", -4)).status_code == 200
    assert held(stocked, headers) == {"arrow": 1}


def test_ac6_a_total_past_what_can_be_stored_is_refused(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    give(stocked, player_id, ("arrow", 2**63 - 1))
    response = give(stocked, player_id, ("arrow", 1))
    assert response.status_code == 422
    assert detail(response).startswith("/items/0/quantity:")
    assert held(stocked, headers) == {"arrow": 2**63 - 1}


@pytest.mark.parametrize("player_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_ac6_a_grant_to_nobody_is_not_found(stocked: TestClient, player_id: str) -> None:
    assert give(stocked, player_id, ("sword", 1)).status_code == 404
    read = stocked.get(f"/api/v1/admin/players/{player_id}/inventory", headers=account(stocked))
    assert read.status_code == 404


@pytest.mark.parametrize(
    ("body", "where"),
    [
        ({}, "/items:"),
        ({"items": []}, "/items:"),
        ({"items": [{"itemId": "sword", "quantity": 0}]}, "/items/0/quantity:"),
        ({"items": [{"itemId": "sword", "quantity": True}]}, "/items/0/quantity:"),
        ({"items": [{"itemId": "sword", "quantity": 1.5}]}, "/items/0/quantity:"),
        ({"items": [{"itemId": "sword", "quantity": 2**63}]}, "/items/0/quantity:"),
        ({"items": [{"itemId": "Sword", "quantity": 1}]}, "/items/0/itemId:"),
        ({"items": ["sword"]}, "/items/0:"),
    ],
)
def test_ac6_a_malformed_grant_names_the_line(
    stocked: TestClient, body: dict[str, Any], where: str
) -> None:
    _, player_id = player(stocked)
    response = stocked.post(
        f"/api/v1/admin/players/{player_id}/inventory/grant", json=body, headers=account(stocked)
    )
    assert response.status_code == 422
    assert detail(response).startswith(where)


def test_ac6_deleting_an_item_takes_it_from_every_player(stocked: TestClient) -> None:
    first, first_id = player(stocked, "device-1")
    second, second_id = player(stocked, "device-2")
    give(stocked, first_id, ("sword", 1), ("arrow", 3))
    give(stocked, second_id, ("sword", 2))

    stocked.delete("/api/v1/admin/items/sword", headers=account(stocked))

    assert held(stocked, first) == {"arrow": 3}
    assert held(stocked, second) == {}


def test_ac6_a_player_cannot_grant_themselves(stocked: TestClient) -> None:
    """Neither through the admin route with their own id, nor through a route of their own,
    because there is none."""
    headers, player_id = player(stocked)
    through_admin = stocked.post(
        f"/api/v1/admin/players/{player_id}/inventory/grant",
        json={"items": [{"itemId": "sword", "quantity": 99}]},
        headers=headers,
    )
    assert through_admin.status_code == 401
    for path in ("/api/v1/player/me/inventory/grant", "/api/v1/player/me/inventory"):
        response = stocked.post(
            path, json={"items": [{"itemId": "sword", "quantity": 99}]}, headers=headers
        )
        assert response.status_code in (404, 405), path
    assert held(stocked, headers) == {}


# --- AC-7: a player's own, and only as themselves ------------------------------------------------


def test_ac7_a_new_player_holds_nothing(client: TestClient) -> None:
    headers, _ = player(client)
    response = client.get("/api/v1/player/me/inventory", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_ac7_a_player_sees_only_their_own(stocked: TestClient) -> None:
    first, first_id = player(stocked, "device-1")
    second, _ = player(stocked, "device-2")
    give(stocked, first_id, ("sword", 1))
    assert held(stocked, first) == {"sword": 1}
    assert held(stocked, second) == {}


def test_ac7_an_editor_reads_what_the_player_reads(stocked: TestClient) -> None:
    headers, player_id = player(stocked)
    give(stocked, player_id, ("sword", 1), ("arrow", 7))
    as_admin = stocked.get(f"/api/v1/admin/players/{player_id}/inventory", headers=account(stocked))
    assert as_admin.status_code == 200
    assert as_admin.json() == stocked.get("/api/v1/player/me/inventory", headers=headers).json()


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_ac7_a_player_token_reaches_no_inventory_admin_route(
    stocked: TestClient, method: str, path: str
) -> None:
    headers, player_id = player(stocked)
    response = stocked.request(
        method,
        path.format(player=player_id),
        json={**SWORD, "items": [{"itemId": "sword", "quantity": 1}]},
        headers=headers,
    )
    assert response.status_code == 401


@pytest.mark.parametrize("kind", ["accessToken", "refreshToken"])
def test_ac7_an_administrators_token_does_not_read_a_players_inventory(
    client: TestClient, kind: str
) -> None:
    player(client)
    token = tokens(client)[kind]
    response = client.get(
        "/api/v1/player/me/inventory", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_ac7_neither_a_key_nor_nothing_reads_an_inventory(client: TestClient) -> None:
    key = mint_key(client)["key"]
    for headers in ({"X-API-Key": key}, {"Authorization": f"Bearer {key}"}, {}):
        assert client.get("/api/v1/player/me/inventory", headers=headers).status_code == 401


def test_ac7_no_player_route_takes_a_player_id(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/player/me/inventory" in paths
    assert [path for path in paths if path.startswith("/api/v1/player") and "{" in path] == []


# --- AC-10: whatever is sent, never a 500 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "where"),
    [
        ({**SWORD, "attributes": '{"note": "a\\u0000b"}'}, "/attributes/note:"),
        ({**SWORD, "attributes": '{"note": "\\ud800"}'}, "/attributes/note:"),
        ({**SWORD, "attributes": '{"damage": NaN}'}, "/attributes:"),
        ({**SWORD, "attributes": '{"damage": 1e1000000}'}, "/attributes/damage:"),
        # Python reads this as 0.0; PostgreSQL's numeric cannot hold it. The database says so,
        # and that is still the caller's 422.
        ({**SWORD, "attributes": '{"damage": 1e-1000000}'}, "/attributes:"),
        ({**SWORD, "attributes": "[" * 5000 + "]" * 5000}, "/attributes:"),
        ({**SWORD, "attributes": '{"a": ' * 200 + "1" + "}" * 200}, "/attributes/a"),
        ({**SWORD, "attributes": json.dumps({"x": "y" * 70_000})}, "/attributes:"),
        ({**SWORD, "name": "Swo\u0000rd"}, "/name:"),
        ({**SWORD, "name": "x" * 256}, "/name:"),
        ({**SWORD, "spriteRef": "x" * 256}, "/spriteRef:"),
        ({**SWORD, "itemType": None}, "/itemType:"),
    ],
)
def test_ac10_an_item_nothing_could_store_is_a_4xx_naming_the_field(
    client: TestClient, body: dict[str, Any], where: str
) -> None:
    response = put_item(client, "sword", body)
    assert response.status_code == 422, response.text
    assert detail(response).startswith(where)
    assert client.get("/api/v1/admin/items/sword", headers=account(client)).status_code == 404


def test_ac10_a_lone_surrogate_sent_raw_is_a_4xx(client: TestClient) -> None:
    """The JSON body itself carries the escape, so the string the route receives holds a
    surrogate that cannot be encoded to reach the database."""
    raw = '{"name": "Sword", "itemType": "weapon", "spriteRef": "\\ud800"}'
    response = client.put(
        "/api/v1/admin/items/sword",
        content=raw.encode(),
        headers={**account(client), "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert detail(response).startswith("/spriteRef:")


DEEP = b"[" * 5000 + b"]" * 5000


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b'"sword"',
        b"{broken",
        b"",
        b'{"name": ' + DEEP + b', "items": ' + DEEP + b"}",
        b'{"name": "Sword", "itemType": "weapon", "spriteRef": '
        + DEEP
        + b', "items": ['
        + DEEP
        + b"]}",
    ],
)
def test_ac10_a_body_that_is_not_a_request_is_a_4xx(client: TestClient, body: bytes) -> None:
    headers = {**account(client), "Content-Type": "application/json"}
    _, player_id = player(client)
    item = client.put("/api/v1/admin/items/sword", content=body, headers=headers)
    grant = client.post(
        f"/api/v1/admin/players/{player_id}/inventory/grant", content=body, headers=headers
    )
    assert 400 <= item.status_code < 500
    assert 400 <= grant.status_code < 500


# --- the contract ---------------------------------------------------------------------------------


def contract_operations() -> list[tuple[str, str, str]]:
    paths = json.loads(CONTRACT.read_text())["paths"]
    return sorted(
        (method.upper(), path, operation["operationId"])
        for path, methods in paths.items()
        for method, operation in methods.items()
        if "/items" in path or "/item-schema" in path or "inventory" in path
    )


def test_every_inventory_operation_in_the_contract_is_served_where_it_says(
    client: TestClient,
) -> None:
    expected = contract_operations()
    assert len(expected) == 9, "the contract's inventory operations, as frozen at v1.0.0"

    served = client.get("/openapi.json").json()["paths"]
    found = []
    for method, path, _ in expected:
        # The contract names every path parameter `id`; the service names them for what they
        # identify. The shape of the path is what a client calls.
        candidates = [
            served_path
            for served_path in served
            if _shape(served_path) == _shape(path) and method.lower() in served[served_path]
        ]
        assert candidates, f"{method} {path} is not served"
        found.append((method, path, served[candidates[0]][method.lower()]["operationId"]))
    assert found == expected

    # The schema route reads its body by hand, so its description is written by hand too.
    body = served["/api/v1/admin/item-schema"]["put"]["requestBody"]
    assert body["content"]["application/json"]["schema"] == {"type": "string"}


def _shape(path: str) -> str:
    return "/".join("{}" if part.startswith("{") else part for part in path.split("/"))
