"""A reward: currencies and XP, together or not at all.

A quest gives forty coins, two gems and a hundred XP. A player who received the coins and not
the gems has been given something the game never offered and cannot be told why, so every part
of a reward is written in one transaction.

The coins are not this app's. They go through the platform's currency port, which the app that
holds currency provides — in this service, the economy, when it is loaded. When none has, a
reward that names a currency is refused whole, before anything is written. Awarding
the XP and dropping the coins would be the partial reward this use case exists to prevent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from wavemaker.apps.progression.application.ports import Progression
from wavemaker.apps.progression.domain.curve import Rejected, Reward, Stage, reached
from wavemaker.platform.currency import Credited, CurrencyLedger


@dataclass(frozen=True, slots=True)
class Rewarded:
    balances: list[Credited]
    xp: int
    stage: Stage | None


def reward(
    progression: Progression,
    ledger: CurrencyLedger | None,
    player: uuid.UUID,
    request: Reward,
) -> Rewarded:
    if request.grants and ledger is None:
        raise Rejected(
            ["/grants: no app in this service holds currency, so a reward cannot include any"]
        )
    balances, xp = progression.reward(player, request.xp, request.grants, ledger)
    return Rewarded(balances=balances, xp=xp, stage=reached(progression.curve(), xp))
