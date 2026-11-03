"""Issuing and reading the kinds of token, and keeping them apart.

There are two JWTs for accounts and they buy very different things. An access token is a bearer
credential: whoever holds it is the caller, for minutes. A refresh token is a claim on a new
session, lives for weeks, and is stored as a digest so a database dump is not a set of live
logins.

**Both carry `typ`, and the check is required rather than advisory.** Two tokens signed by the
same key with the same subject are interchangeable unless something says they are not. Without
`typ`, a refresh token — the long-lived one — works as a bearer credential, which quietly turns
a weeks-long claim into a weeks-long session. Nothing fails; the system is simply much weaker
than its design says.

**A third kind, the player token, is kept apart the same way.** It is what a game client gets
for an API key: short-lived, scoped to one player, carrying no role, and the only credential
that reaches a player's state. It has its own `typ` and its own reader, so an administrator's
token is not a player and a player's token is not an administrator, in either direction — and
neither depends on a reader happening to notice a missing claim.

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
from typing import Any

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
    PLAYER = "player"


class TokenError(PlatformError):
    """A token was absent, expired, tampered with, or of the wrong kind."""


@dataclass(frozen=True, slots=True)
class Caller:
    """Who is making this request, as proved by a token rather than claimed by a body."""

    kind: TokenKind
    subject: uuid.UUID
    project: uuid.UUID
    role: Role


@dataclass(frozen=True, slots=True)
class PlayerCaller:
    """The player a request acts as, as proved by a player token.

    A different type from `Caller` on purpose. Every admin guard takes a `Caller`, so a player
    cannot reach one by type confusion, and a player has no role to be checked or forgotten.
    """

    player: uuid.UUID
    project: uuid.UUID


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
    if kind is TokenKind.PLAYER:
        raise TokenError("A player token is issued with issue_player and carries no role.")
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
    """Decode an account's token and insist it is the kind the caller asked for."""
    if expect is TokenKind.PLAYER:
        # A player is not an account with no role. Reading one through here would hand back a
        # Caller, the type every admin guard trusts.
        raise TokenError("A player token is read with read_player, never as an account.")

    claims = _claims(token, secret, expect)
    try:
        role = Role(claims["rol"])
        subject = uuid.UUID(claims["sub"])
        project = uuid.UUID(claims["prj"])
    except (KeyError, ValueError) as unusable:
        raise TokenError("This token does not describe a caller this build knows.") from unusable

    return Caller(kind=expect, subject=subject, project=project, role=role)


def issue_player(
    *,
    secret: str,
    player: uuid.UUID,
    project: uuid.UUID,
    lifetime: timedelta,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """A token that acts as one player, and when it stops working.

    Short-lived because it authorises writes and cannot be revoked: like an access token it is
    checked by its signature and nothing else, which is what makes it cheap, and therefore valid
    until it expires whatever happens. A token lifted off a device should stop being useful
    quickly.
    """
    issued = now or datetime.now(UTC)
    expires = issued + lifetime
    claims = {
        "jti": uuid.uuid4().hex,
        "typ": TokenKind.PLAYER.value,
        "sub": str(player),
        "prj": str(project),
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM), expires


def read_player(token: str, *, secret: str) -> PlayerCaller:
    """Decode a player token, refusing every other kind."""
    claims = _claims(token, secret, TokenKind.PLAYER)
    try:
        player = uuid.UUID(claims["sub"])
        project = uuid.UUID(claims["prj"])
    except (KeyError, ValueError, TypeError) as unusable:
        raise TokenError("This token does not describe a player this build knows.") from unusable
    return PlayerCaller(player=player, project=project)


def _claims(token: str, secret: str, expect: TokenKind) -> dict[str, Any]:
    if not token.isascii():
        # A token this service issued is ASCII. Anything else cannot be one, and the decoder
        # would fail on a lone surrogate while encoding it, before it could say so itself.
        raise TokenError("This token could not be read.")
    try:
        claims: dict[str, Any] = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as expired:
        raise TokenError("This token has expired.") from expired
    except jwt.InvalidTokenError as invalid:
        raise TokenError("This token could not be read.") from invalid

    kind = claims.get("typ")
    if kind != expect.value:
        # The whole reason `typ` exists. A refresh token presented as a bearer credential is
        # not a weaker session, it is a different thing being accepted as this one — and the
        # same holds for a player presented as an administrator, or the reverse.
        raise TokenError(f"Expected a {expect.value} token, got {kind or 'one with no kind'}.")
    return claims
