"""Signing in, renewing, and what happens when a renewed token comes back.

Against a real database, because every interesting rule here is about a row: a stored digest,
a revoked_at that was or was not set, a second sign-in that must not reset a password.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from wavemaker.platform.config import Settings
from wavemaker.platform.http.factory import create_app

SECRET = "an-integration-test-signing-key-not-for-anything-real"  # keel:allow-secret
EMAIL = "admin@example.test"
PASSWORD = "correct-horse-battery-staple"  # keel:allow-secret


def settings_for(database_url: str) -> Settings:
    return Settings(
        plugins_directory=None,
        database_url=database_url,
        jwt_secret=SECRET,
        admin_email=EMAIL,
        admin_password=PASSWORD,
    )


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings_for(database_url))) as running:
        yield running


def sign_in(client: TestClient, password: str = PASSWORD) -> dict[str, Any]:
    response = client.post("/api/v1/auth/token", json={"email": EMAIL, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_the_bootstrap_administrator_can_sign_in(client: TestClient) -> None:
    body = sign_in(client)
    assert body["tokenType"] == "Bearer"
    assert body["accessToken"] and body["refreshToken"]
    assert body["accessTokenExpiresAt"].endswith("Z")


def test_the_wrong_password_is_refused(client: TestClient) -> None:
    refused = client.post("/api/v1/auth/token", json={"email": EMAIL, "password": "nope"})
    assert refused.status_code == 401


def test_an_address_with_no_account_is_refused_the_same_way(client: TestClient) -> None:
    """The same answer as a wrong password, so this route cannot be used to ask which
    addresses have accounts."""
    unknown = client.post(
        "/api/v1/auth/token", json={"email": "nobody@example.test", "password": PASSWORD}
    )
    wrong = client.post("/api/v1/auth/token", json={"email": EMAIL, "password": "nope"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_an_address_is_matched_whatever_case_it_is_typed_in(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token", json={"email": "ADMIN@Example.TEST", "password": PASSWORD}
    )
    assert response.status_code == 200


def test_me_says_who_the_access_token_proves_you_are(client: TestClient) -> None:
    token = sign_in(client)["accessToken"]
    body = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["role"] == "ADMIN"
    # What v1 answered for a signed-in account, not the token's internal kind.
    assert body["kind"] == "USER"


def test_me_without_a_token_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401


def test_a_refresh_token_is_not_accepted_as_a_bearer_credential(client: TestClient) -> None:
    """The long-lived token must not open a session by being presented as the short-lived one."""
    refresh = sign_in(client)["refreshToken"]
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {refresh}"})
    assert response.status_code == 401


def test_an_access_token_cannot_be_used_to_renew(client: TestClient) -> None:
    access = sign_in(client)["accessToken"]
    answer = client.post("/api/v1/auth/refresh", json={"refreshToken": access})
    assert answer.status_code == 401


def test_renewing_gives_a_new_pair(client: TestClient) -> None:
    first = sign_in(client)
    renewed = client.post("/api/v1/auth/refresh", json={"refreshToken": first["refreshToken"]})
    assert renewed.status_code == 200
    assert renewed.json()["refreshToken"] != first["refreshToken"], "the token must rotate"


def test_a_renewed_token_cannot_be_renewed_twice(client: TestClient) -> None:
    first = sign_in(client)["refreshToken"]
    client.post("/api/v1/auth/refresh", json={"refreshToken": first})
    again = client.post("/api/v1/auth/refresh", json={"refreshToken": first})
    assert again.status_code == 401


def test_presenting_a_rotated_token_ends_every_session_for_that_account(
    client: TestClient,
) -> None:
    """A rotated token coming back means the client lost a race or somebody else has a copy,
    and from here those look the same. Signing in again is an annoyance; leaving a stolen
    token working for weeks is not."""
    first = sign_in(client)["refreshToken"]
    second = client.post("/api/v1/auth/refresh", json={"refreshToken": first}).json()

    client.post("/api/v1/auth/refresh", json={"refreshToken": first})  # the stolen one

    # The honest client's token, issued legitimately, is now dead too.
    honest = client.post("/api/v1/auth/refresh", json={"refreshToken": second["refreshToken"]})
    assert honest.status_code == 401


def test_a_token_this_service_never_issued_is_refused(client: TestClient) -> None:
    """Signed with the right key, but no row. A token whose session was never recorded, or was
    pruned, is not a session."""
    from datetime import timedelta
    from uuid import uuid4

    from wavemaker.platform.identity.tokens import Role, TokenKind, issue

    forged, _ = issue(
        secret=SECRET,
        kind=TokenKind.REFRESH,
        subject=uuid4(),
        project=client.app.state.project_id,  # type: ignore[attr-defined]
        role=Role.ADMIN,
        lifetime=timedelta(days=1),
    )
    answer = client.post("/api/v1/auth/refresh", json={"refreshToken": forged})
    assert answer.status_code == 401


def test_only_a_digest_of_a_refresh_token_is_stored(client: TestClient) -> None:
    """A database dump must be a list of sessions that existed, not a set of usable ones."""
    token = sign_in(client)["refreshToken"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        stored = session.execute(text("select token_digest from refresh_token")).scalars().all()
    assert token not in stored
    assert all(len(digest) == 64 for digest in stored)


def test_restarting_does_not_reset_the_administrator_password(database_url: str) -> None:
    """Startup provisions the account every time. It must not undo a password somebody changed,
    or the environment at deploy time silently becomes the password forever."""
    with TestClient(create_app(settings_for(database_url))) as first:
        sign_in(first)
        with first.app.state.session_factory() as session:  # type: ignore[attr-defined]
            session.execute(
                text("update account set password_hash = 'not-a-valid-hash' where email = :e"),
                {"e": EMAIL},
            )
            session.commit()

    with TestClient(create_app(settings_for(database_url))) as second:
        refused = second.post("/api/v1/auth/token", json={"email": EMAIL, "password": PASSWORD})
        assert refused.status_code == 401, "startup overwrote the stored password"


def test_a_database_without_a_signing_key_refuses_to_start(database_url: str) -> None:
    """Rather than booting and issuing tokens anyone holding this source could forge."""
    from wavemaker.platform.kernel.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        create_app(Settings(plugins_directory=None, database_url=database_url, jwt_secret=""))


def test_with_no_database_signing_in_says_so_rather_than_refusing_the_password() -> None:
    """503, not 401. Telling a caller their credentials were wrong when nothing could ever
    accept them is a lie that costs somebody an afternoon."""
    with TestClient(create_app(Settings(plugins_directory=None))) as client:
        response = client.post("/api/v1/auth/token", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 503
