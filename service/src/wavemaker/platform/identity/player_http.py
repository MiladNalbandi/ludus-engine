"""API keys, player sessions, and the player's own profile.

Three credentials meet here and none of them stands in for another:

    X-API-Key: wm_...         what a game build holds. Buys a player session, and nothing else.
    Bearer <player token>     what a player holds. Reaches /api/v1/player/me and nothing else.
    Bearer <access token>     what an account holds. Reaches /api/v1/admin/** by role.

The key travels in its own header rather than in `Authorization`. The two have different
holders, lifetimes and powers, and one header carrying either makes "which kind of caller is
this" a parsing question rather than a routing one.

Platform routes rather than an app's, for the same reason the player table is the platform's:
every player-facing app needs a player, and apps may not import each other.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from wavemaker.platform import paging
from wavemaker.platform.identity import api_keys, players
from wavemaker.platform.identity.api_keys import ApiKey
from wavemaker.platform.identity.http import CurrentPlayer, Database, moment, requires
from wavemaker.platform.identity.players import Player, PlayerError
from wavemaker.platform.identity.tokens import Role, issue_player
from wavemaker.platform.kernel.storable import storable

router = APIRouter(prefix="/api/v1", tags=["players"])

# Issuing credentials is an administrator's job, not an editor's. An editor decides what players
# receive; deciding who may call the service at all is a different power.
ADMINISTRATOR = Depends(requires(Role.ADMIN))

# Reading players is an editor's job, as every /admin/players route is: the editor decides what
# players receive, and needs to see who they are to do it.
EDITOR = Depends(requires(Role.EDITOR, Role.ADMIN))

PLAYERS_PER_PAGE = 50
MOST_PLAYERS_PER_PAGE = 200

ApiKeyHeader = Annotated[str | None, Header(alias="X-API-Key")]


def _api_key(db: Database, presented: ApiKeyHeader = None) -> ApiKey:
    session, project, _ = db
    key = api_keys.authenticate(session, project, (presented or "").strip())
    if key is None:
        # Missing, unknown and revoked are one answer. Which of them it was is not something
        # a holder of a leaked or stale key needs to learn.
        raise HTTPException(status_code=401, detail="A valid API key is required.")
    return key


GameKey = Annotated[ApiKey, Depends(_api_key)]


def _refused(problem: PlayerError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(problem))


def _profile(player: Player) -> dict[str, Any]:
    return {
        "id": str(player.id),
        "externalId": player.external_id,
        "displayName": player.display_name,
        "createdAt": moment(player.created_at),
        "lastSeenAt": moment(player.last_seen_at),
    }


def _key_summary(key: ApiKey) -> dict[str, Any]:
    return {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.prefix,
        "role": key.role.value,
        "createdAt": moment(key.created_at),
        "revokedAt": None if key.revoked_at is None else moment(key.revoked_at),
    }


# --- a game build buys a player session -----------------------------------------------------


@router.post("/public/players/session")
def start_player_session(body: dict[str, Any], db: Database, _: GameKey) -> dict[str, Any]:
    """Under /public because a game calls it, and unlike the rest of /public it needs a key.

    Published content needs no credential because every copy of the game downloads it. Minting
    a credential is a different act, and requiring a key here is what lets an operator cut off a
    compromised build by revoking it.
    """
    session, project, settings = db
    try:
        external_id = players.external_id_of(body.get("externalId"))
    except PlayerError as problem:
        raise _refused(problem) from problem

    player = players.start(session, project, external_id)
    token, expires = issue_player(
        secret=settings.jwt_secret,
        player=player.id,
        project=project,
        lifetime=settings.player_lifetime(),
    )
    return {
        "playerId": str(player.id),
        "externalId": player.external_id,
        "displayName": player.display_name,
        "token": token,
        "expiresAt": moment(expires),
    }


# --- a player, about themselves ---------------------------------------------------------------


@router.get("/player/me")
def get_player_self(caller: CurrentPlayer, db: Database) -> dict[str, Any]:
    session, project, _ = db
    player = players.find(session, project, caller.player)
    if player is None:
        # The token is valid and the player is gone: removed mid-session. 404 rather than 401,
        # because the credential is not the problem and signing in again will not fix it.
        raise HTTPException(status_code=404, detail="This player no longer exists.")
    return _profile(player)


@router.patch("/player/me")
def rename_player_self(
    body: dict[str, Any], caller: CurrentPlayer, db: Database
) -> dict[str, Any]:
    session, project, _ = db
    try:
        name = players.display_name_of(body.get("displayName"))
    except PlayerError as problem:
        raise _refused(problem) from problem

    renamed = players.rename(session, project, caller.player, name)
    if renamed is None:
        raise HTTPException(status_code=404, detail="This player no longer exists.")
    return _profile(renamed)


# --- an editor, about players ----------------------------------------------------------------


def _player_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    """The key of the last player on the previous page.

    The time travels at full precision. The Java sent epoch milliseconds while PostgreSQL keeps
    microseconds, so of two players seen in the same millisecond either side of a page boundary,
    the second sorted after a truncated cursor it should have sorted before, and was skipped.
    """
    if cursor is None or not cursor.strip():
        return None
    try:
        seen, player_id = paging.decode_cursor(cursor.strip(), 2)
        last_seen = datetime.fromisoformat(seen)
        if last_seen.tzinfo is None:
            raise ValueError("a cursor's time carries its zone")
        return last_seen, uuid.UUID(player_id)
    except (paging.BadCursor, ValueError) as broken:
        raise HTTPException(
            status_code=422, detail="/cursor: not a cursor this service issued"
        ) from broken


@router.get("/admin/players", dependencies=[EDITOR], operation_id="listPlayers")
def list_players(
    db: Database, cursor: str | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Most recently seen first, a keyset page at a time. No offsets: the ordering column moves
    every time somebody plays."""
    session, project, _ = db
    after = _player_cursor(cursor)
    size = paging.page_size(limit, default=PLAYERS_PER_PAGE, maximum=MOST_PLAYERS_PER_PAGE)
    # One more than asked for, so whether there is a next page needs no second query.
    found = players.page(session, project, after, size + 1)
    shown = found[:size]
    last = shown[-1] if len(found) > size else None
    return {
        "players": [_profile(player) for player in shown],
        "total": players.count(session, project),
        "nextCursor": None
        if last is None
        else paging.encode_cursor(last.last_seen_at.isoformat(), str(last.id)),
    }


@router.get("/admin/players/{id}", dependencies=[EDITOR], operation_id="getPlayer")
def get_player(player_id: Annotated[str, Path(alias="id")], db: Database) -> dict[str, Any]:
    session, project, _ = db
    try:
        parsed: uuid.UUID | None = uuid.UUID(player_id)
    except ValueError:
        parsed = None
    found = None if parsed is None else players.find(session, project, parsed)
    if found is None:
        # "Not an id" and "not in this project" are one answer, as they are for keys.
        raise HTTPException(status_code=404, detail="No such player.")
    return _profile(found)


# --- an administrator, about keys -------------------------------------------------------------


@router.get("/admin/api-keys", dependencies=[ADMINISTRATOR])
def list_api_keys(db: Database) -> list[dict[str, Any]]:
    session, project, _ = db
    return [_key_summary(key) for key in api_keys.list_keys(session, project)]


@router.post("/admin/api-keys", dependencies=[ADMINISTRATOR])
def create_api_key(body: dict[str, Any], db: Database) -> dict[str, Any]:
    """200 rather than 201: the frozen contract says 200, and it is the contract a generated
    client was built from. The Java answered 201 here, which is a drift in the Java."""
    session, project, _ = db
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="/name: a key needs a name a person can read")
    storable("/name", name)
    if len(name.strip()) > api_keys.MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"/name: a key's name is at most {api_keys.MAX_NAME_LENGTH} characters",
        )

    created = api_keys.issue(session, project, name.strip())
    # ApiKeyCreated has no revokedAt: a key that has just been minted has not been revoked.
    summary = {k: v for k, v in _key_summary(created.key).items() if k != "revokedAt"}
    return {**summary, "key": created.secret}


@router.delete("/admin/api-keys/{key_id}", dependencies=[ADMINISTRATOR])
def revoke_api_key(key_id: str, db: Database) -> dict[str, Any]:
    session, project, _ = db
    try:
        parsed = uuid.UUID(key_id)
    except ValueError:
        parsed = None
    revoked = None if parsed is None else api_keys.revoke(session, project, parsed)
    if revoked is None:
        # 404 for "not there" and for "not an id", alike. Telling a caller a key exists but is
        # somebody else's is the leak.
        raise HTTPException(status_code=404, detail="No such API key.")
    return _key_summary(revoked)
