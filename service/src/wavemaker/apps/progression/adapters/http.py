"""The progression routes: the curve an editor defines, a player's own progress, and rewards.

**A player reads their progress and cannot add to it.** There is no player route that writes
XP, for the reason there is none that grants currency: anything a game client can do, anybody
who unpacked the game can do, and XP a client could award itself is XP a modified binary
decides. Rewards are an editor's, behind a credential that does not ship inside the game.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path

from wavemaker.apps.progression.adapters.postgres import PostgresProgression
from wavemaker.apps.progression.application.ports import Progression
from wavemaker.apps.progression.application.rewards import reward
from wavemaker.apps.progression.domain.curve import (
    NoSuchPlayer,
    ProgressionError,
    Rejected,
    Stage,
    curve_of,
    progress,
    reward_of,
)
from wavemaker.platform import currency
from wavemaker.platform.currency import Credited
from wavemaker.platform.identity import players
from wavemaker.platform.identity.http import CurrentPlayer, Database, moment, requires
from wavemaker.platform.identity.tokens import Role

curve_router = APIRouter(prefix="/api/v1/admin/xp-curve", tags=["Players"])
player_router = APIRouter(prefix="/api/v1/player/me", tags=["Players"])
admin_router = APIRouter(prefix="/api/v1/admin/players", tags=["Players"])

# Editing the curve and awarding XP decide what players receive, as granting currency does.
EDITOR = Depends(requires(Role.EDITOR, Role.ADMIN))


def get_progression(db: Database) -> Progression:
    session, project, _ = db
    return PostgresProgression(session, project)


Store = Annotated[Progression, Depends(get_progression)]


def _stage(stage: Stage | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    return {"stage": stage.stage, "xpRequired": stage.xp_required, "label": stage.label}


def _curve(stages: list[Stage]) -> dict[str, Any]:
    return {"stages": [_stage(stage) for stage in stages]}


def _balance(balance: Credited) -> dict[str, Any]:
    return {
        "currency": balance.currency,
        "amount": balance.amount,
        "updatedAt": moment(balance.updated_at),
    }


def _rejected(problem: Rejected) -> HTTPException:
    # Every problem at once, each led by its pointer: an author fixes them in one pass.
    return HTTPException(status_code=422, detail=problem.problems)


# --- the curve --------------------------------------------------------------------------------


@curve_router.get("", dependencies=[EDITOR], operation_id="getXpCurve")
def get_xp_curve(progression: Store) -> dict[str, Any]:
    """Empty when the project has defined none; a player then has no stage."""
    return _curve(progression.curve())


@curve_router.put("", dependencies=[EDITOR], operation_id="replaceXpCurve")
def replace_xp_curve(body: dict[str, Any], progression: Store) -> dict[str, Any]:
    try:
        stages = curve_of(body.get("stages"))
    except Rejected as problem:
        raise _rejected(problem) from problem
    return _curve(progression.replace_curve(stages))


# --- a player, on themselves ------------------------------------------------------------------


@player_router.get("/progress", operation_id="getPlayerProgress")
def get_player_progress(caller: CurrentPlayer, progression: Store, db: Database) -> dict[str, Any]:
    session, project, _ = db
    if players.find(session, project, caller.player) is None:
        raise HTTPException(status_code=404, detail="This player no longer exists.")
    where = progress(progression.curve(), progression.xp(caller.player))
    return {"xp": where.xp, "stage": _stage(where.stage), "nextStage": _stage(where.next_stage)}


# --- an editor, rewarding somebody ------------------------------------------------------------


@admin_router.post("/{id}/reward", dependencies=[EDITOR], operation_id="rewardPlayer")
def reward_player(
    player_id: Annotated[str, Path(alias="id")], body: dict[str, Any], progression: Store
) -> dict[str, Any]:
    """All or nothing: one refused grant rolls back the whole reward, XP included."""
    try:
        player = uuid.UUID(player_id)
    except ValueError as unknown:
        raise HTTPException(status_code=404, detail="No such player.") from unknown
    try:
        given = reward(progression, currency.provided(), player, reward_of(body))
    except Rejected as problem:
        raise _rejected(problem) from problem
    except NoSuchPlayer as missing:
        raise HTTPException(status_code=404, detail="No such player.") from missing
    except ProgressionError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
    return {
        "balances": [_balance(balance) for balance in given.balances],
        "xp": given.xp,
        "stage": _stage(given.stage),
    }
