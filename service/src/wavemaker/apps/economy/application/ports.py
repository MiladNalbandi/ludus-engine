"""What the economy needs from storage, said as an interface rather than a table.

Crediting and debiting are two methods rather than one `adjust(delta)`. They are different
acts with different callers — an editor credits, a player debits — and a single method taking a
signed number is one sign error away from a player crediting themselves.

There is no in-memory implementation, unlike content. The rules this port exists to keep — no
lost grant under concurrency, no balance below zero — are kept by PostgreSQL, and a fake would
be a second implementation of exactly the rules the database is trusted with, passing tests the
real one might fail.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from wavemaker.apps.economy.domain.wallet import Balance


class Wallets(Protocol):
    def balances(self, player: uuid.UUID) -> Sequence[Balance]:
        """Every currency this player holds, by currency name. Empty for a player with none,
        and for a player who is not there — a wallet does not know who exists."""

    def grant(self, player: uuid.UUID, currency: str, amount: int) -> Balance:
        """Add to a balance, creating it on the first grant.

        Raises `NoSuchPlayer` when the player is not in this project, and `TooLarge` when the
        result would not fit."""

    def spend(self, player: uuid.UUID, currency: str, amount: int) -> Balance:
        """Take from a balance. Raises `NotEnough` when it does not cover the amount, including
        when there is no balance at all."""
