"""The whole R1 path at once: a real database, the real app, over HTTP.

Everything here is covered a layer down — the repository has its own tests, the routes have
theirs against an in-memory repository. What only this can catch is the shape of failure where
every part works and the system does not: a migration that never ran, a session never opened,
an ETag computed from rows the client was not served.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app

NOW = datetime(2026, 9, 13, 16, 58, 40, tzinfo=UTC)
FIRST = '{"id":"first","schema_version":1,"b":1,"a":2.0,"name":"First Steps"}'
SECOND = '{"id":"second","schema_version":1,"name":"Crossfire"}'


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            plugins_directory=None,
            database_url=database_url,
            # A database implies a signing key: the service refuses to start without one.
            jwt_secret="a-content-test-signing-key-of-a-respectable-length",  # keel:allow-secret
        )
    )
    _seed(app.state.session_factory, app.state.project_id)
    with TestClient(app) as running:
        yield running


def _seed(session_factory, project: uuid.UUID) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        for wave_id, name, order, published, document in [
            ("first", "First Steps", 0, True, FIRST),
            ("second", "Crossfire", 1, True, SECOND),
            ("draft", "Pressure", 2, False, '{"id":"draft"}'),
        ]:
            session.execute(
                text("""
                    insert into wave (project_id, wave_id, schema_uri, schema_version, name,
                                      wave_order, published, config_json, created_at, updated_at)
                    values (:p, :w, 'https://ludus/schema/wave/v1', 1, :n, :o, :pub, :d, :t, :t)
                """),
                {
                    "p": project,
                    "w": wave_id,
                    "n": name,
                    "o": order,
                    "pub": published,
                    "d": document,
                    "t": NOW,
                },
            )
        level = uuid.uuid4()
        session.execute(
            text("""
                insert into wave_level (id, project_id, name, active, created_at, updated_at)
                values (:i, :p, 'Act One', true, :t, :t)
            """),
            {"i": level, "p": project, "t": NOW},
        )
        for position, wave_id in enumerate(["first", "second", "draft"]):
            session.execute(
                text("""
                    insert into wave_level_wave (project_id, wave_level_id, wave_id, position)
                    values (:p, :l, :w, :pos)
                """),
                {"p": project, "l": level, "w": wave_id, "pos": position},
            )
        session.commit()


def test_the_service_migrates_itself_and_serves_what_is_in_the_database(
    client: TestClient,
) -> None:
    body = client.get("/api/v1/public/waves").json()
    assert [wave["id"] for wave in body] == ["first", "second"]


def test_a_document_arrives_byte_for_byte_from_the_database(client: TestClient) -> None:
    """Through SQLAlchemy, FastAPI and the HTTP stack, with the float and the key order intact."""
    response = client.get("/api/v1/public/waves/first/raw")
    assert response.content == FIRST.encode()


def test_the_status_hash_still_equals_the_list_etag_over_real_rows(client: TestClient) -> None:
    status = client.get("/api/v1/public/status").json()["contentHash"]
    assert client.get("/api/v1/public/waves").headers["etag"] == f'"{status}"'


def test_a_client_that_revalidates_gets_a_304(client: TestClient) -> None:
    etag = client.get("/api/v1/public/waves").headers["etag"]
    assert client.get("/api/v1/public/waves", headers={"If-None-Match": etag}).status_code == 304


def test_publishing_another_wave_moves_the_hash(client: TestClient) -> None:
    """The poll's whole purpose: a client told nothing changed must hear when it does."""
    before = client.get("/api/v1/public/status").json()["contentHash"]

    factory = client.app.state.session_factory  # type: ignore[attr-defined]
    with factory() as session:
        session.execute(text("update wave set published = true where wave_id = 'draft'"))
        session.commit()

    after = client.get("/api/v1/public/status").json()["contentHash"]
    assert after != before
    assert len(client.get("/api/v1/public/waves").json()) == 3


def test_a_draft_is_404_over_the_real_stack(client: TestClient) -> None:
    assert client.get("/api/v1/public/waves/draft").status_code == 404
    assert client.get("/api/v1/public/waves/draft/raw").status_code == 404


def test_the_active_level_serves_only_published_waves(client: TestClient) -> None:
    body = client.get("/api/v1/public/wave-levels/active").json()
    assert body["name"] == "Act One"
    assert [wave["id"] for wave in body["waves"]] == ["first", "second"]


def test_a_batch_comes_back_in_the_order_asked_for(client: TestClient) -> None:
    body = client.post("/api/v1/public/waves/batch", json={"ids": ["second", "draft", "first"]})
    assert list(body.json()) == ["second", "first"]


def test_health_reports_the_content_app(client: TestClient) -> None:
    assert {"name": "content", "version": "1.0.0"} in client.get("/health").json()["apps"]
