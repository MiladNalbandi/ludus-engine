"""Issue #85: text that no PostgreSQL value can hold is the caller's 422, never a 500.

Two kinds of string reach this service as valid JSON and cannot go any further: one holding a
NUL (`\\u0000`), which a `text` value cannot contain, and one holding a lone surrogate
(`\\ud800`), which is not a character and cannot be encoded to be sent at all. Before this
change each route that stored or looked up client text found that out from the driver, as a
500. Now every one of them answers 422 naming the field, and nothing is written.

The bodies are sent as JSON text with the escapes in it, the way a client sends them. A
surrogate cannot be passed through `json=`: the client would fail to encode it before sending.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.players import (
    ADMIN,
    EDITOR,
    PASSWORD,
    account,
    mint_key,
    player,
    serving,
)

NUL = "Swo\u0000rd"
SURROGATE = "Swo\ud800rd"
UNSTORABLE = pytest.mark.parametrize(
    ("value", "reason"),
    [(NUL, "NUL"), (SURROGATE, "surrogate")],
    ids=["NUL", "lone surrogate"],
)

SAMPLES = Path(__file__).resolve().parents[3] / "samples" / "waves"


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def send(
    client: TestClient, method: str, path: str, body: Any, headers: dict[str, str]
) -> Any:
    """`body` as JSON text with every non-ASCII character escaped, which is valid JSON even for
    a lone surrogate."""
    return client.request(
        method,
        path,
        content=json.dumps(body, ensure_ascii=True).encode(),
        headers={**headers, "Content-Type": "application/json"},
    )


def refused_at(response: Any, pointer: str, reason: str) -> None:
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    problems = detail if isinstance(detail, list) else [detail]
    named = [problem for problem in problems if problem.startswith(f"{pointer}: ")]
    assert named, f"no problem at {pointer}: {problems}"
    assert reason in named[0], named[0]


def a_wave(wave_id: str, order: int, **changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((SAMPLES / "demo_first_steps.json").read_text())
    document["id"] = wave_id
    document["progression_config"]["order"] = order
    document.update(changes)
    return document


# --- the three routes the issue names ---------------------------------------------------------


@UNSTORABLE
def test_a_display_name_that_cannot_be_stored_is_422_and_the_name_is_unchanged(
    client: TestClient, value: str, reason: str
) -> None:
    headers, _ = player(client)
    named = client.patch("/api/v1/player/me", json={"displayName": "Ada"}, headers=headers)
    assert named.status_code == 200, named.text

    response = send(client, "PATCH", "/api/v1/player/me", {"displayName": value}, headers)

    refused_at(response, "/displayName", reason)
    assert client.get("/api/v1/player/me", headers=headers).json()["displayName"] == "Ada"


@UNSTORABLE
def test_an_api_key_name_that_cannot_be_stored_is_422_and_no_key_is_minted(
    client: TestClient, value: str, reason: str
) -> None:
    response = send(client, "POST", "/api/v1/admin/api-keys", {"name": value}, account(client))

    refused_at(response, "/name", reason)
    assert client.get("/api/v1/admin/api-keys", headers=account(client)).json() == []


@UNSTORABLE
def test_an_external_id_that_cannot_be_stored_is_422_and_no_player_is_made(
    client: TestClient, value: str, reason: str
) -> None:
    key = mint_key(client)["key"]
    response = send(
        client, "POST", "/api/v1/public/players/session", {"externalId": value}, {"X-API-Key": key}
    )

    refused_at(response, "/externalId", reason)
    listed = client.get("/api/v1/admin/players", headers=account(client, EDITOR)).json()
    assert listed["total"] == 0


# --- every other route that stores client text ------------------------------------------------


@UNSTORABLE
def test_a_board_name_that_cannot_be_stored_is_422(
    client: TestClient, value: str, reason: str
) -> None:
    editor = account(client, EDITOR)
    response = send(client, "PUT", "/api/v1/admin/leaderboards/high_score", {"name": value}, editor)

    refused_at(response, "/name", reason)
    assert client.get("/api/v1/admin/leaderboards", headers=editor).json() == []


@UNSTORABLE
def test_a_stage_label_that_cannot_be_stored_is_422_at_its_index(
    client: TestClient, value: str, reason: str
) -> None:
    editor = account(client, EDITOR)
    stages = [{"stage": 1, "xpRequired": 0}, {"stage": 2, "xpRequired": 10, "label": value}]
    response = send(client, "PUT", "/api/v1/admin/xp-curve", {"stages": stages}, editor)

    refused_at(response, "/stages/1/label", reason)
    assert client.get("/api/v1/admin/xp-curve", headers=editor).json() == {"stages": []}


@UNSTORABLE
@pytest.mark.parametrize(
    ("body", "pointer"),
    [
        (lambda bad: {"name": bad, "waves": []}, "/name"),
        (lambda bad: {"name": "Act One", "description": bad, "waves": []}, "/description"),
        (lambda bad: {"name": "Act One", "waves": [bad]}, "/waves/0"),
    ],
    ids=["name", "description", "a wave id"],
)
def test_a_level_that_cannot_be_stored_is_422_naming_the_field(
    client: TestClient, value: str, reason: str, body: Any, pointer: str
) -> None:
    response = send(client, "POST", "/api/v1/admin/wave-levels", body(value), account(client))

    refused_at(response, pointer, reason)
    assert client.get("/api/v1/admin/wave-levels", headers=account(client)).json() == []


@UNSTORABLE
@pytest.mark.parametrize(
    ("changes", "pointer"),
    [
        (lambda bad: {"name": bad}, "/name"),
        (lambda bad: {"description": bad}, "/description"),
        (lambda bad: {"version": bad}, "/version"),
    ],
    ids=["an indexed field", "a field kept only in the document", "another"],
)
def test_a_wave_that_cannot_be_stored_is_422_naming_the_field(
    client: TestClient, value: str, reason: str, changes: Any, pointer: str
) -> None:
    """The document is kept as the text that arrived, and a `jsonb` column is generated from
    it. A NUL escaped as `\\u0000` is six harmless characters in the text and a value `jsonb`
    refuses, so the check reads the document, not only the fields lifted out of it."""
    headers = account(client)
    created = send(client, "POST", "/api/v1/admin/waves", a_wave("w", 0, **changes(value)), headers)
    refused_at(created, pointer, reason)

    assert send(client, "POST", "/api/v1/admin/waves", a_wave("w", 0), headers).status_code == 201
    replaced = send(
        client, "PUT", "/api/v1/admin/waves/w", a_wave("w", 0, **changes(value)), headers
    )
    refused_at(replaced, pointer, reason)

    imported = send(
        client, "POST", "/api/v1/admin/waves/bulk", [a_wave("v", 1, **changes(value))], headers
    )
    refused_at(imported, f"/0{pointer}", reason)
    assert [wave["id"] for wave in client.get("/api/v1/admin/waves", headers=headers).json()] == [
        "w"
    ]


# --- routes that look client text up -----------------------------------------------------------


@UNSTORABLE
@pytest.mark.parametrize("field", ["email", "password"])
def test_signing_in_with_text_that_cannot_be_stored_is_422(
    client: TestClient, value: str, reason: str, field: str
) -> None:
    body = {"email": ADMIN, "password": PASSWORD, field: value}
    refused_at(send(client, "POST", "/api/v1/auth/token", body, {}), f"/{field}", reason)


@UNSTORABLE
def test_a_refresh_token_that_cannot_be_one_is_refused_as_unreadable(
    client: TestClient, value: str, reason: str
) -> None:
    response = send(client, "POST", "/api/v1/auth/refresh", {"refreshToken": value}, {})
    assert response.status_code == 401, response.text


@UNSTORABLE
@pytest.mark.parametrize(
    ("path", "headers"),
    [("/api/v1/admin/waves/batch-delete", True), ("/api/v1/public/waves/batch", False)],
    ids=["batch delete", "batch read"],
)
def test_a_batch_naming_a_wave_that_cannot_exist_is_422_at_its_index(
    client: TestClient, value: str, reason: str, path: str, headers: bool
) -> None:
    response = send(
        client, "POST", path, {"ids": ["fine", value]}, account(client) if headers else {}
    )
    refused_at(response, "/ids/1", reason)


# --- the boundary, for the route that forgets --------------------------------------------------


@UNSTORABLE
def test_the_database_boundary_refuses_unstorable_text_before_sending_it(
    session_factory: sessionmaker[Session], value: str, reason: str
) -> None:
    """Every engine the service builds checks the text it is about to send, whatever route sent
    it. The route that names the field gives the better answer; this one makes sure a route
    nobody remembered to check still gives the caller's answer, not the driver's."""
    from wavemaker.platform.kernel.storable import UnstorableText

    with session_factory() as session:
        with pytest.raises(UnstorableText, match=reason):
            session.execute(text("select :value"), {"value": value})
        with pytest.raises(UnstorableText, match=reason):
            session.execute(
                text("select :value"), [{"value": "fine"}, {"value": value}]
            )
        # Bytes are not text, and a NUL in a blob is a byte like any other.
        assert session.execute(text("select :value"), {"value": b"\x00"}).scalar_one() == b"\x00"
        assert session.execute(text("select :value"), {"value": "fine"}).scalar_one() == "fine"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/waves/w%00x",
        "/api/v1/public/waves/w%00x",
        "/api/v1/admin/waves/w%00x/publish",
    ],
)
def test_a_path_naming_a_wave_with_a_nul_in_it_is_a_4xx(client: TestClient, path: str) -> None:
    """No route reads this field by name, so nothing names it: the database boundary refuses
    the text before it is sent. What matters is that it is the caller's answer, not a 500."""
    method = "POST" if path.endswith("/publish") else "GET"
    response = client.request(method, path, headers=account(client))
    assert 400 <= response.status_code < 500, response.text
