"""Signing in, renewing, and asking who you are.

These routes belong to the platform rather than to an app: every app relies on knowing who is
calling, and an app that shipped its own sign-in would be a second place for the rules to drift.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from wavemaker.platform.identity import sessions
from wavemaker.platform.identity.sessions import TokenPair
from wavemaker.platform.identity.tokens import (
    Caller,
    PlayerCaller,
    Role,
    TokenError,
    TokenKind,
    read,
    read_player,
)

router = APIRouter(prefix="/api/v1", tags=["identity"])

Authorization = Annotated[str | None, Header(alias="Authorization")]


def database(request: Request) -> Iterator[tuple[Session, uuid.UUID, Any]]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        # Not "unauthorised": there is no account store at all, and telling a caller their
        # credentials were wrong when nothing could ever accept them is a lie that costs
        # somebody an afternoon.
        raise HTTPException(status_code=503, detail="This service has no database configured.")
    with factory() as session:
        yield session, request.app.state.project_id, request.app.state.settings


Database = Annotated[tuple[Session, uuid.UUID, Any], Depends(database)]


def _pair(pair: TokenPair) -> dict[str, Any]:
    return {
        "accessToken": pair.access_token,
        "tokenType": "Bearer",
        "accessTokenExpiresAt": moment(pair.access_expires_at),
        "refreshToken": pair.refresh_token,
        "refreshTokenExpiresAt": moment(pair.refresh_expires_at),
    }


def moment(value: datetime) -> str:
    """`...Z`, the way the frozen contract writes a date-time."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@router.post("/auth/token")
def sign_in(body: dict[str, Any], db: Database) -> dict[str, Any]:
    session, project, settings = db
    try:
        pair = sessions.sign_in(
            session,
            project,
            str(body.get("email", "")),
            str(body.get("password", "")),
            secret=settings.jwt_secret,
            access_lifetime=settings.access_lifetime(),
            refresh_lifetime=settings.refresh_lifetime(),
        )
    except TokenError as refused:
        raise HTTPException(status_code=401, detail=str(refused)) from refused
    return _pair(pair)


@router.post("/auth/refresh")
def refresh(body: dict[str, Any], db: Database) -> dict[str, Any]:
    session, project, settings = db
    try:
        pair = sessions.refresh_session(
            session,
            project,
            str(body.get("refreshToken", "")),
            secret=settings.jwt_secret,
            access_lifetime=settings.access_lifetime(),
            refresh_lifetime=settings.refresh_lifetime(),
        )
    except TokenError as refused:
        raise HTTPException(status_code=401, detail=str(refused)) from refused
    return _pair(pair)


def current_caller(request: Request, authorization: Authorization = None) -> Caller:
    """The caller this request proved it is, or a 401.

    Deny by default: every path out of here that is not a valid access token raises. There is
    no branch that returns an anonymous caller, because a route that forgot to check a role
    would then run as one.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="This service cannot verify credentials.")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="A bearer token is required.")

    try:
        # ACCESS, insisted on. A refresh token is a weeks-long claim on a new session, and
        # accepting one here would silently turn it into a weeks-long session.
        return read(authorization[7:].strip(), secret=settings.jwt_secret, expect=TokenKind.ACCESS)
    except TokenError as refused:
        raise HTTPException(status_code=401, detail=str(refused)) from refused


CurrentCaller = Annotated[Caller, Depends(current_caller)]


def current_player(request: Request, authorization: Authorization = None) -> PlayerCaller:
    """The player this request acts as, or a 401.

    The only way a route reaches a player's state. The player comes from a verified player
    token and from nothing in the request, which is why no player route takes a player id: a
    route shaped `/players/{id}` and authorised by "is a player" lets any player act as any
    other, and the check that stops it is one somebody must remember to write in every handler.

    An administrator's token is refused here, not translated. An administrator acting on a
    player does it through an admin route, which records that it was an administrator.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="This service cannot verify credentials.")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="A player session token is required.")

    try:
        caller = read_player(authorization[7:].strip(), secret=settings.jwt_secret)
    except TokenError as refused:
        raise HTTPException(status_code=401, detail=str(refused)) from refused

    if caller.project != request.app.state.project_id:
        raise HTTPException(status_code=401, detail="This token belongs to another project.")
    return caller


CurrentPlayer = Annotated[PlayerCaller, Depends(current_player)]


def requires(*allowed: Role):  # type: ignore[no-untyped-def]
    """A dependency that admits only these roles. 403, not 404: the caller is known."""

    def guard(caller: CurrentCaller) -> Caller:
        if caller.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"This needs one of: {', '.join(role.value for role in allowed)}.",
            )
        return caller

    return guard


@router.get("/me")
def who_am_i(caller: CurrentCaller) -> dict[str, str]:
    return {
        "kind": caller.kind.value,
        "subject": str(caller.subject),
        "project": str(caller.project),
        "role": caller.role.value,
    }
