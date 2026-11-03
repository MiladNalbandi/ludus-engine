"""What the player and economy tests share: a service, its accounts, and a way to be a player.

Plain functions rather than fixtures, so each test module states its own `client` fixture and a
reader can see what a test is running against without opening a conftest.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app
from wavemaker.platform.identity.accounts import ensure_account
from wavemaker.platform.identity.tokens import Role

SECRET = "a-players-test-signing-key-of-respectable-length"  # keel:allow-secret
PASSWORD = "correct-horse-battery-staple"  # keel:allow-secret
ADMIN = "admin@example.test"
EDITOR = "editor@example.test"
VIEWER = "viewer@example.test"


@contextmanager
def serving(database_url: str) -> Iterator[TestClient]:
    """The whole service, with an administrator, an editor and a viewer."""
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
        ensure_account(session, app.state.project_id, EDITOR, PASSWORD, Role.EDITOR)
        ensure_account(session, app.state.project_id, VIEWER, PASSWORD, Role.VIEWER)
    with TestClient(app) as running:
        yield running


def tokens(client: TestClient, email: str = ADMIN) -> dict[str, Any]:
    response = client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def account(client: TestClient, email: str = ADMIN) -> dict[str, str]:
    """Headers for a signed-in account: an administrative access token."""
    return {"Authorization": f"Bearer {tokens(client, email)['accessToken']}"}


def mint_key(client: TestClient, name: str = "android-client") -> dict[str, Any]:
    response = client.post("/api/v1/admin/api-keys", json={"name": name}, headers=account(client))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def start_session(
    client: TestClient, key: str, external_id: str = "device-0001"
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/public/players/session",
        json={"externalId": external_id},
        headers={"X-API-Key": key},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def player(client: TestClient, external_id: str = "device-0001") -> tuple[dict[str, str], str]:
    """Headers acting as one player, and that player's id."""
    session = start_session(client, mint_key(client)["key"], external_id)
    return {"Authorization": f"Bearer {session['token']}"}, str(session["playerId"])
