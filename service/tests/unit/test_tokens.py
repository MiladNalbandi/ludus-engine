"""The two token kinds, and the claim that keeps them apart.

Two JWTs signed by the same key with the same subject are interchangeable unless something
says they are not. The `typ` claim is that something, and these tests exist because its absence
would break nothing visibly: a refresh token would simply work as a bearer credential, turning
a weeks-long claim into a weeks-long session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from wavemaker.platform.identity.tokens import Role, TokenError, TokenKind, issue, read

SECRET = "a-test-signing-key-that-is-not-a-real-one"  # keel:allow-secret
# Long enough to keep PyJWT from warning: the point of these tests is the claim
# checking, not the key length, and a warning per run teaches people to ignore them.
ANOTHER_SECRET = "a-different-key-of-a-respectable-length-for-hs256"  # keel:allow-secret
SUBJECT = uuid.uuid4()
PROJECT = uuid.uuid4()


def a_token(kind: TokenKind, *, role: Role = Role.ADMIN, lifetime_minutes: int = 15) -> str:
    token, _ = issue(
        secret=SECRET,
        kind=kind,
        subject=SUBJECT,
        project=PROJECT,
        role=role,
        lifetime=timedelta(minutes=lifetime_minutes),
    )
    return token


def test_an_access_token_reads_back_as_the_caller_it_was_issued_for() -> None:
    caller = read(a_token(TokenKind.ACCESS), secret=SECRET, expect=TokenKind.ACCESS)
    assert caller.subject == SUBJECT
    assert caller.project == PROJECT
    assert caller.role is Role.ADMIN
    assert caller.kind is TokenKind.ACCESS


def test_a_refresh_token_is_not_an_access_token() -> None:
    """The point of the whole file. Presented as a bearer credential, it must be refused."""
    with pytest.raises(TokenError, match="access"):
        read(a_token(TokenKind.REFRESH), secret=SECRET, expect=TokenKind.ACCESS)


def test_an_access_token_is_not_a_refresh_token() -> None:
    """And the other direction, so the check is a rule rather than one branch that happens to
    be there."""
    with pytest.raises(TokenError, match="refresh"):
        read(a_token(TokenKind.ACCESS), secret=SECRET, expect=TokenKind.REFRESH)


def test_a_token_with_no_kind_at_all_is_refused() -> None:
    """A token from an older build, or one somebody made. Either way, not a caller."""
    forged = jwt.encode(
        {
            "sub": str(SUBJECT),
            "prj": str(PROJECT),
            "rol": "ADMIN",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        read(forged, secret=SECRET, expect=TokenKind.ACCESS)


def test_an_expired_token_is_refused() -> None:
    with pytest.raises(TokenError, match="expired"):
        read(a_token(TokenKind.ACCESS, lifetime_minutes=-1), secret=SECRET, expect=TokenKind.ACCESS)


def test_a_token_signed_with_another_key_is_refused() -> None:
    with pytest.raises(TokenError):
        read(a_token(TokenKind.ACCESS), secret=ANOTHER_SECRET, expect=TokenKind.ACCESS)


def test_a_role_this_build_does_not_have_is_refused_rather_than_ignored() -> None:
    """Deny by default. An unknown role is a token from another system or a tampered one, and
    treating it as "a caller with no permissions" makes it a caller."""
    forged = jwt.encode(
        {
            "typ": "access",
            "sub": str(SUBJECT),
            "prj": str(PROJECT),
            "rol": "SUPERUSER",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        read(forged, secret=SECRET, expect=TokenKind.ACCESS)


def test_a_tampered_payload_is_refused() -> None:
    token = a_token(TokenKind.ACCESS, role=Role.VIEWER)
    header, _payload, signature = token.split(".")
    other = jwt.encode(
        {"typ": "access", "rol": "ADMIN"}, ANOTHER_SECRET, algorithm="HS256"
    ).split(".")[1]
    with pytest.raises(TokenError):
        read(f"{header}.{other}.{signature}", secret=SECRET, expect=TokenKind.ACCESS)


def test_only_editors_and_administrators_may_write() -> None:
    assert Role.ADMIN.may_write()
    assert Role.EDITOR.may_write()
    assert not Role.VIEWER.may_write()
