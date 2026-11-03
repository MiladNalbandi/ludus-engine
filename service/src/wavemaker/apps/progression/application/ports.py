"""What progression needs from storage, said as an interface rather than a table.

No in-memory implementation, for the economy's reason: the rules worth testing — an award is
never lost to a concurrent one, and a reward is all or nothing — are kept by PostgreSQL's
transactions, and a fake would be a second implementation of exactly those.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from wavemaker.apps.progression.domain.curve import Grant, Stage
from wavemaker.platform.currency import Credited, CurrencyLedger


class Progression(Protocol):
    def curve(self) -> list[Stage]:
        """The project's curve, in ascending order. Empty when it has none."""

    def replace_curve(self, stages: Sequence[Stage]) -> list[Stage]:
        """Replace the whole curve. Concurrent replacements are serialised, so the last one
        wins whole rather than two of them interleaving into a curve nobody sent."""

    def xp(self, player: uuid.UUID) -> int:
        """A player's XP; zero for one who has never been awarded any."""

    def reward(
        self,
        player: uuid.UUID,
        xp: int,
        grants: Sequence[Grant],
        ledger: CurrencyLedger | None,
    ) -> tuple[list[Credited], int]:
        """Add `xp` and credit every grant through `ledger`, in one transaction, and return
        the balances it left and the player's XP after it.

        Any refusal rolls back all of it. Raises `NoSuchPlayer`, `TooMuchXp`, and `Rejected`
        naming the grant a ledger refused."""
