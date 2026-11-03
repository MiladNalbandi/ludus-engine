"""Issuing and reading the two kinds of token, and keeping them apart.

There are two JWTs here and they buy very different things. An access token is a bearer
credential: whoever holds it is the caller, for minutes. A refresh token is a claim on a new
session, lives for weeks, and is stored as a digest so a database dump is not a set of live
logins.

**Both carry `typ`, and the check is required rather than advisory.** Two tokens signed by the
same key with the same subject are interchangeable unless something says they are not. Without
`typ`, a refresh token — the long-lived one — works as a bearer credential, which quietly turns
a weeks-long claim into a weeks-long session. Nothing fails; the system is simply much weaker
than its design says.

The role is read back through the same enum it was written from, so a token carrying a role
this build does not have is refused rather than treated as a caller with no permissions. Deny
by default: an unknown role is a token from another system or a tampered one, and neither is a
caller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt

from wavemaker.platform.kernel.errors import PlatformError

ALGORITHM = "HS256"

# RFC 7518 §3.2: an HMAC key should be at least as long as the hash it feeds. A shorter
# signing key is not a warning worth printing once at startup and forgetting; it is the one
# secret that lets anybody mint an administrator.
MINIMUM_SECRET_BYTES = 32


class Role(StrEnum):
    VIEWER = "VIEWER"
    EDITOR = "EDITOR"
    ADMIN = "ADMIN"

    def may_write(self) -> bool:
        return self in (Role.EDITOR, Role.ADMIN)


class TokenKind(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(PlatformError):
    """A token was absent, expired, tampered with, or of the wrong kind."""


@dataclass(frozen=True, slots=True)
class Caller:
    """Who is making this request, as proved by a token rather than claimed by a body."""

    kind: TokenKind
    subject: uuid.UUID
    project: uuid.UUID
    role: Role


def issue(
    *,
    secret: str,
    kind: TokenKind,
    subject: uuid.UUID,
    project: uuid.UUID,
    role: Role,
    lifetime: timedelta,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued = now or datetime.now(UTC)
    expires = issued + lifetime
    claims = {
        # A unique id per issuance. Without it two tokens minted in the same second for the
        # same account are byte-identical — same subject, same role, same second — and a
        # refresh token's digest is its primary key, so the second one cannot be stored. The
        # test for "renewing gives a new pair" is what found this.
        "jti": uuid.uuid4().hex,
        "typ": kind.value,
        "sub": str(subject),
        "prj": str(project),
        "rol": role.value,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM), expires


def read(token: str, *, secret: str, expect: TokenKind) -> Caller:
    """Decode a token and insist it is the kind the caller asked for."""
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as expired:
        raise TokenError("This token has expired.") from expired
    except jwt.InvalidTokenError as invalid:
        raise TokenError("This token could not be read.") from invalid

    kind = claims.get("typ")
    if kind != expect.value:
        # The whole reason `typ` exists. A refresh token presented as a bearer credential is
        # not a weaker session, it is a different thing being accepted as this one.
        raise TokenError(f"Expected a {expect.value} token, got {kind or 'one with no kind'}.")

    try:
        role = Role(claims["rol"])
        subject = uuid.UUID(claims["sub"])
        project = uuid.UUID(claims["prj"])
    except (KeyError, ValueError) as unusable:
        raise TokenError("This token does not describe a caller this build knows.") from unusable

    return Caller(kind=TokenKind(kind), subject=subject, project=project, role=role)
