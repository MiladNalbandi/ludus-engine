"""AC-3: a player token is its own kind, and is not an administrator's token in either direction.

All three tokens are signed by the same key. Without `typ` checked on both sides they differ only
in which claims they happen to carry, and a reader that tolerated a missing role would accept a
player as an administrator — or an administrator as any player they liked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from wavemaker.platform.identity.tokens import (
    Role,
    TokenError,
    TokenKind,
    issue,
    issue_player,
    read,
    read_player,
)

SECRET = "a-test-signing-key-that-is-not-a-real-one"  # keel:allow-secret
PLAYER = uuid.uuid4()
PROJECT = uuid.uuid4()


def a_player_token(lifetime: timedelta = timedelta(hours=1)) -> str:
    token, _ = issue_player(secret=SECRET, player=PLAYER, project=PROJECT, lifetime=lifetime)
    return token


def an_account_token(kind: TokenKind) -> str:
    token, _ = issue(
        secret=SECRET,
        kind=kind,
        subject=PLAYER,  # the same uuid on purpose: only the kind may tell them apart
        project=PROJECT,
        role=Role.ADMIN,
        lifetime=timedelta(minutes=15),
    )
    return token


def test_ac3_a_player_token_reads_back_as_the_player_it_was_issued_for() -> None:
    caller = read_player(a_player_token(), secret=SECRET)
    assert caller.player == PLAYER
    assert caller.project == PROJECT


def test_ac3_a_player_token_says_it_is_one_and_carries_no_role() -> None:
    """A player has no role and cannot be given one. A role claim on this token would be one
    more thing a reader might trust."""
    claims = jwt.decode(a_player_token(), SECRET, algorithms=["HS256"])
    assert claims["typ"] == "player"
    assert "rol" not in claims


def test_ac3_a_player_token_is_not_an_access_token() -> None:
    with pytest.raises(TokenError):
        read(a_player_token(), secret=SECRET, expect=TokenKind.ACCESS)


def test_ac3_a_player_token_is_not_a_refresh_token() -> None:
    with pytest.raises(TokenError):
        read(a_player_token(), secret=SECRET, expect=TokenKind.REFRESH)


@pytest.mark.parametrize("kind", [TokenKind.ACCESS, TokenKind.REFRESH])
def test_ac3_an_account_token_is_not_a_player_token(kind: TokenKind) -> None:
    """The other direction. An administrator's token naming a player's uuid as its subject
    must not act as that player."""
    with pytest.raises(TokenError, match="player"):
        read_player(an_account_token(kind), secret=SECRET)


def test_ac3_a_player_token_with_its_kind_removed_is_refused() -> None:
    claims = jwt.decode(a_player_token(), SECRET, algorithms=["HS256"])
    del claims["typ"]
    stripped = jwt.encode(claims, SECRET, algorithm="HS256")
    with pytest.raises(TokenError):
        read_player(stripped, secret=SECRET)


def test_ac3_a_player_token_signed_with_another_key_is_refused() -> None:
    forged, _ = issue_player(
        secret="a-different-key-of-a-respectable-length-for-hs256",  # keel:allow-secret
        player=PLAYER,
        project=PROJECT,
        lifetime=timedelta(hours=1),
    )
    with pytest.raises(TokenError):
        read_player(forged, secret=SECRET)


def test_ac3_an_expired_player_token_is_refused() -> None:
    token, _ = issue_player(
        secret=SECRET,
        player=PLAYER,
        project=PROJECT,
        lifetime=timedelta(minutes=5),
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    with pytest.raises(TokenError, match="expired"):
        read_player(token, secret=SECRET)


def test_ac3_two_player_tokens_for_one_player_in_one_second_differ() -> None:
    """The R2 lesson, kept: without a unique id per issuance, two tokens minted in the same
    second are byte-identical."""
    now = datetime.now(UTC)
    first, _ = issue_player(
        secret=SECRET, player=PLAYER, project=PROJECT, lifetime=timedelta(hours=1), now=now
    )
    second, _ = issue_player(
        secret=SECRET, player=PLAYER, project=PROJECT, lifetime=timedelta(hours=1), now=now
    )
    assert first != second
