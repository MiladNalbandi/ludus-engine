"""Wallets: what each player holds of each currency, and the two ways it changes.

The app exposes one `router` to the platform, which mounts it without knowing what is on it.
Players themselves are not here. They are the platform's, because inventory and leaderboards
need them too and apps may not import each other; this app only knows a player by the id a
verified token or an editor gives it.

It also provides the platform's currency ledger when it is loaded, which is how a reward from
`progression` pays coins without either app importing the other.
"""

from fastapi import APIRouter

from wavemaker.apps.economy.adapters.http import admin_router, get_wallets, player_router
from wavemaker.apps.economy.adapters.postgres import PostgresLedger
from wavemaker.platform import currency

router = APIRouter()
router.include_router(player_router)
router.include_router(admin_router)

currency.provide(PostgresLedger())

__all__ = ["get_wallets", "router"]
