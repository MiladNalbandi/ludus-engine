"""Application configuration over HTTP: the settings every client fetches at launch.

The last three operations of the frozen contract the Python did not serve, found by walking the
whole of `docs/api/openapi-v1.json` against this service (R9). These are the Java's
`AppConfigIntegrationTest` and its rows of `AuthorisationMatrixTest`, carried over.

The two claims worth the file: the bytes survive the round trip, because the tag every client
checks is a hash of them; and a body that is not a document is the caller's 422, never a 500.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.players import EDITOR, VIEWER, account, player, serving

ADMIN_CONFIG = "/api/v1/admin/app-config"
PUBLIC_CONFIG = "/api/v1/public/app-config"


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with serving(database_url) as running:
        yield running


def put(client: TestClient, body: bytes | str) -> int:
    response = client.put(
        ADMIN_CONFIG,
        content=body,
        headers={**account(client, EDITOR), "Content-Type": "application/json"},
    )
    return int(response.status_code)


def test_the_bytes_a_client_receives_are_the_bytes_an_editor_sent(client: TestClient) -> None:
    awkward = b'{"spawnRate":1.0,   "z":true,\n  "a":[1,2,3]}'

    assert put(client, awkward) == 200

    served = client.get(PUBLIC_CONFIG)
    assert served.status_code == 200
    # Whitespace, key order and 1.0-versus-1 all survive, or the tag moves for nothing.
    assert served.content == awkward
    assert client.get(ADMIN_CONFIG, headers=account(client, EDITOR)).content == awkward


def test_the_replace_answers_with_the_document_it_stored(client: TestClient) -> None:
    response = client.put(
        ADMIN_CONFIG,
        content=b'{"difficulty":"normal"}',
        headers={**account(client, EDITOR), "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.content == b'{"difficulty":"normal"}'


def test_a_project_never_configured_has_an_empty_object_not_a_404(client: TestClient) -> None:
    assert client.get(PUBLIC_CONFIG).content == b"{}"
    assert client.get(ADMIN_CONFIG, headers=account(client)).content == b"{}"


def test_the_config_is_cacheable_and_answers_304(client: TestClient) -> None:
    put(client, '{"difficulty":"normal"}')

    etag = client.get(PUBLIC_CONFIG).headers["ETag"]
    assert etag

    revalidated = client.get(PUBLIC_CONFIG, headers={"If-None-Match": etag})
    assert revalidated.status_code == 304
    assert revalidated.content == b""
    assert revalidated.headers["ETag"] == etag


def test_editing_the_config_moves_the_etag(client: TestClient) -> None:
    put(client, '{"difficulty":"normal"}')
    before = client.get(PUBLIC_CONFIG).headers["ETag"]

    put(client, '{"difficulty":"hard"}')

    assert client.get(PUBLIC_CONFIG).headers["ETag"] != before
    assert client.get(PUBLIC_CONFIG, headers={"If-None-Match": before}).status_code == 200


def test_saving_the_same_bytes_keeps_the_etag(client: TestClient) -> None:
    put(client, '{"difficulty":"normal"}')
    before = client.get(PUBLIC_CONFIG).headers["ETag"]

    put(client, '{"difficulty":"normal"}')

    assert client.get(PUBLIC_CONFIG).headers["ETag"] == before


@pytest.mark.parametrize("body", [b"", b"   \n"])
def test_an_empty_request_body_is_a_422_rather_than_a_500(client: TestClient, body: bytes) -> None:
    assert put(client, body) == 422


def test_malformed_json_is_a_422_naming_where_it_stops_parsing(client: TestClient) -> None:
    response = client.put(
        ADMIN_CONFIG,
        content=b'{"difficulty":}',
        headers={**account(client, EDITOR), "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    # The parser's line and column are the only genuinely useful part of its message.
    assert "line" in response.json()["detail"]


@pytest.mark.parametrize(
    "body", [b'{"name":"a\\u0000b"}', b'{"a\\u0000":1}', b'{"name":"\\ud800"}', b"\xff\xfe"]
)
def test_text_postgresql_cannot_hold_is_a_422_and_stores_nothing(
    client: TestClient, body: bytes
) -> None:
    assert put(client, body) == 422
    assert client.get(PUBLIC_CONFIG).content == b"{}"


def test_a_refused_replace_leaves_the_last_document_in_place(client: TestClient) -> None:
    put(client, '{"difficulty":"normal"}')
    assert put(client, "{") == 422
    assert client.get(PUBLIC_CONFIG).content == b'{"difficulty":"normal"}'


def test_the_public_route_needs_no_credential_and_the_admin_route_does(
    client: TestClient,
) -> None:
    assert client.get(PUBLIC_CONFIG).status_code == 200
    assert client.get(ADMIN_CONFIG).status_code == 401
    answer = client.put(ADMIN_CONFIG, content=b"{}")
    assert answer.status_code == 401


def test_configuration_is_edited_by_the_people_who_edit_content(client: TestClient) -> None:
    """The Java's authorisation matrix: viewers are refused, editors and administrators are
    not, and a player's token is not an account's."""
    viewer = account(client, VIEWER)
    assert client.get(ADMIN_CONFIG, headers=viewer).status_code == 403
    answer = client.put(ADMIN_CONFIG, content=b"{}", headers=viewer)
    assert answer.status_code == 403

    for allowed in (account(client, EDITOR), account(client)):
        assert client.get(ADMIN_CONFIG, headers=allowed).status_code == 200

    as_player, _ = player(client)
    assert client.get(ADMIN_CONFIG, headers=as_player).status_code in (401, 403)


def test_the_stored_document_is_also_queryable_as_jsonb(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """The generated column, which only PostgreSQL has and which nothing may serve from."""
    put(client, '{"difficulty": "hard", "lives": 3}')
    with session_factory() as session:
        lives = session.execute(text("select config ->> 'lives' from app_config")).scalar_one()
        generated = session.execute(
            text("""
                select is_generated from information_schema.columns
                where table_name = 'app_config' and column_name = 'config'
            """)
        ).scalar_one()
    assert lives == "3"
    assert generated == "ALWAYS"


def test_the_configuration_belongs_to_a_project_and_there_is_one_per_project(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        constraints: dict[str, str] = dict(
            session.execute(
                text("""
                    select contype::text, pg_get_constraintdef(oid) from pg_constraint
                    where conrelid = cast('app_config' as regclass) and contype in ('p', 'f')
                """)
            ).all()
        )
    assert constraints["p"] == "PRIMARY KEY (project_id)"
    assert constraints["f"].startswith("FOREIGN KEY (project_id) REFERENCES project(id)")
