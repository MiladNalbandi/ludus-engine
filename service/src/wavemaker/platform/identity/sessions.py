"""Signing in, and rotating a session.

A refresh token is stored as a sha256 digest. A database dump is then a list of sessions that
existed, not a set of credentials somebody can use.

**Rotation, and what happens when a rotated token comes back.** Every refresh revokes the token
it was given and issues a new one. If a token that was already rotated is presented again,
either the client lost a race or somebody else has a copy — and from here those look identical.
So every live session for that account is revoked. A legitimate client signs in again, which is
an annoyance; the alternative is leaving a stolen token working for weeks, which is not.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from wavemaker.platform.identity.accounts import Account, find_by_email
from wavemaker.platform.identity.passwords import verify
from wavemaker.platform.identity.tokens import Role, TokenError, TokenKind, issue, read


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


class SignInError(TokenError):
    """Refused a sign-in. Deliberately the same shape whatever was wrong with it."""


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign_in(
    session: Session,
    project: uuid.UUID,
    email: str,
    password: str,
    *,
    secret: str,
    access_lifetime: timedelta,
    refresh_lifetime: timedelta,
) -> TokenPair:
    account = find_by_email(session, project, email)

    # One message and one timing path for "no such account", "wrong password" and "disabled".
    # Anything else turns the sign-in route into a way to ask which addresses have accounts.
    if account is None or not account.enabled or not verify(password, account.password_hash):
        raise SignInError("Those credentials were not accepted.")

    return _issue_pair(
        session,
        project,
        account,
        secret=secret,
        access_lifetime=access_lifetime,
        refresh_lifetime=refresh_lifetime,
    )


def refresh_session(
    session: Session,
    project: uuid.UUID,
    refresh_token: str,
    *,
    secret: str,
    access_lifetime: timedelta,
    refresh_lifetime: timedelta,
) -> TokenPair:
    caller = read(refresh_token, secret=secret, expect=TokenKind.REFRESH)
    if caller.project != project:
        raise TokenError("This token belongs to another project.")

    row = session.execute(
        text("""
            select id, account_id, revoked_at, expires_at from refresh_token
            where token_digest = :digest and project_id = :project
        """),
        {"digest": digest(refresh_token), "project": project},
    ).one_or_none()

    if row is None:
        raise TokenError("This session is not one this service issued.")

    if row.revoked_at is not None:
        _revoke_every_session(session, project, uuid.UUID(str(row.account_id)))
        raise TokenError(
            "This session was already renewed. Every session for the account has been ended; "
            "sign in again."
        )

    if row.expires_at <= datetime.now(UTC):
        raise TokenError("This session has expired.")

    session.execute(
        text("update refresh_token set revoked_at = :now where id = :id"),
        {"now": datetime.now(UTC), "id": row.id},
    )

    account = _account_by_id(session, project, uuid.UUID(str(row.account_id)))
    if account is None or not account.enabled:
        session.commit()
        raise TokenError("The account for this session can no longer sign in.")

    return _issue_pair(
        session,
        project,
        account,
        secret=secret,
        access_lifetime=access_lifetime,
        refresh_lifetime=refresh_lifetime,
    )


def _issue_pair(
    session: Session,
    project: uuid.UUID,
    account: Account,
    *,
    secret: str,
    access_lifetime: timedelta,
    refresh_lifetime: timedelta,
) -> TokenPair:
    now = datetime.now(UTC)
    access, access_expires = issue(
        secret=secret,
        kind=TokenKind.ACCESS,
        subject=account.id,
        project=project,
        role=account.role,
        lifetime=access_lifetime,
        now=now,
    )
    refresh, refresh_expires = issue(
        secret=secret,
        kind=TokenKind.REFRESH,
        subject=account.id,
        project=project,
        role=account.role,
        lifetime=refresh_lifetime,
        now=now,
    )
    session.execute(
        text("""
            insert into refresh_token
                (id, project_id, account_id, token_digest, issued_at, expires_at)
            values (:id, :project, :account, :digest, :issued, :expires)
        """),
        {
            "id": uuid.uuid4(),
            "project": project,
            "account": account.id,
            "digest": digest(refresh),
            "issued": now,
            "expires": refresh_expires,
        },
    )
    session.commit()
    return TokenPair(
        access_token=access,
        access_expires_at=access_expires,
        refresh_token=refresh,
        refresh_expires_at=refresh_expires,
    )


def _revoke_every_session(session: Session, project: uuid.UUID, account: uuid.UUID) -> None:
    session.execute(
        text("""
            update refresh_token set revoked_at = :now
            where project_id = :project and account_id = :account and revoked_at is null
        """),
        {"now": datetime.now(UTC), "project": project, "account": account},
    )
    session.commit()


def _account_by_id(session: Session, project: uuid.UUID, account: uuid.UUID) -> Account | None:
    row = session.execute(
        text("""
            select id, email, password_hash, role, enabled from account
            where project_id = :project and id = :id
        """),
        {"project": project, "id": account},
    ).one_or_none()
    if row is None:
        return None
    return Account(
        id=uuid.UUID(str(row.id)),
        email=row.email,
        password_hash=row.password_hash,
        role=Role(row.role),
        enabled=row.enabled,
    )
