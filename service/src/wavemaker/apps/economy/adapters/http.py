"""The wallet routes: a player's own, and an editor's.

**A player may spend and may not be granted, and that asymmetry is the trust model.** A forged
spend costs the person who forged it, so it is safe on a route a game client calls. A forged
grant would make the currency whatever a modified binary says it is, so crediting is an admin
route, behind a credential that does not ship inside the game. A game with no server of its
own therefore cannot award currency through this service — a real limit, stated plainly rather
than a hole left open to avoid admitting it.

The player routes are `/me` and take no player id, so there is no handler that could forget to
check that the id is the caller's. The admin routes take an id, because an editor acts on
somebody else by definition.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from wavemaker.apps.economy.adapters.postgres import PostgresWallets
from wavemaker.apps.economy.application.ports import Wallets
from wavemaker.apps.economy.domain.wallet import (
    Balance,
    EconomyError,
    NoSuchPlayer,
    currency_code,
    positive_amount,
)
from wavemaker.platform.identity import players
from wavemaker.platform.identity.http import CurrentPlayer, Database, requires
from wavemaker.platform.identity.tokens import Role

player_router = APIRouter(prefix="/api/v1/player/me", tags=["economy"])
admin_router = APIRouter(prefix="/api/v1/admin/players", tags=["economy"])

# Crediting is an editor's job: it decides what players receive, like authoring content does.
# A viewer may not look either, as in the Java, where every /admin/players route is an editor's.
EDITOR = Depends(requires(Role.EDITOR, Role.ADMIN))


def get_wallets(db: Database) -> Wallets:
    """The request's own session, shared with anything else in the request that asks for it.

    With no database configured the platform answers 503 before this runs. An empty wallet
    would tell a player they own nothing, which is a different and untrue thing.
    """
    session, project, _ = db
    return PostgresWallets(session, project)


Store = Annotated[Wallets, Depends(get_wallets)]


def _moment(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _balance(balance: Balance) -> dict[str, Any]:
    return {
        "currency": balance.currency,
        "amount": balance.amount,
        "updatedAt": _moment(balance.updated_at),
    }


def _wallet(balances: list[Balance]) -> dict[str, Any]:
    return {"balances": [_balance(balance) for balance in balances]}


def _change(body: dict[str, Any]) -> tuple[str, int]:
    """The currency and amount of a grant or a spend, or a 422 naming the field."""
    try:
        return currency_code(body.get("currency")), positive_amount(body.get("amount"))
    except EconomyError as invalid:
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid


def _player_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as unknown:
        raise HTTPException(status_code=404, detail="No such player.") from unknown


# --- a player, on their own wallet -----------------------------------------------------------


@player_router.get("/wallet")
def get_player_wallet(caller: CurrentPlayer, wallets: Store) -> dict[str, Any]:
    """Read-only. Awarding currency needs a credential that does not ship in the game."""
    return _wallet(list(wallets.balances(caller.player)))


@player_router.post("/wallet/spend")
def spend_player_currency(
    body: dict[str, Any], caller: CurrentPlayer, wallets: Store
) -> dict[str, Any]:
    """Refused with a 422 when the balance does not cover it, rather than clamped to zero. A
    clamped spend would let a client buy what it cannot pay for, with this service agreeing."""
    currency, amount = _change(body)
    try:
        return _balance(wallets.spend(caller.player, currency, amount))
    except EconomyError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused


# --- an editor, on somebody's wallet ---------------------------------------------------------


@admin_router.get("/{player_id}/wallet", dependencies=[EDITOR])
def get_player_wallet_as_admin(player_id: str, wallets: Store, db: Database) -> dict[str, Any]:
    player = _player_id(player_id)
    session, project, _ = db
    # A wallet does not know who exists, and an empty one is the normal state of a new player,
    # so whether there is a player at all is the platform's question.
    if players.find(session, project, player) is None:
        raise HTTPException(status_code=404, detail="No such player.")
    return _wallet(list(wallets.balances(player)))


@admin_router.post("/{player_id}/wallet/grant", dependencies=[EDITOR])
def grant_player_currency(player_id: str, body: dict[str, Any], wallets: Store) -> dict[str, Any]:
    """Editors and above. Not available to a game client in any form."""
    player = _player_id(player_id)
    currency, amount = _change(body)
    try:
        return _balance(wallets.grant(player, currency, amount))
    except NoSuchPlayer as missing:
        raise HTTPException(status_code=404, detail="No such player.") from missing
    except EconomyError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
