"""Crediting currency from outside the app that holds it.

A reward is coins and XP together, all or nothing: a player who got the coins and not the XP
has been given something the game never offered. XP belongs to `progression` and coins to
`economy`, and apps may not import each other. This is the port between them, owned by the
platform because only the platform can be imported by both.

The app that holds currency *provides* a ledger. Any app may then credit it, inside the
caller's own transaction, so a refusal anywhere in a reward rolls back every part of it.

The economy app provides one when it is loaded. When nothing has — no app holding currency is
loaded — `provided()` is `None`, and a caller must say so rather than drop the coins.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from wavemaker.platform.kernel.errors import PlatformError


@dataclass(frozen=True, slots=True)
class Credited:
    """A balance after a credit."""

    currency: str
    amount: int
    updated_at: datetime


class CurrencyRefused(PlatformError):
    """The ledger understood the credit and will not make it: a currency it does not accept,
    a balance that would not fit, a player it cannot credit. The message is for a person."""


class CurrencyLedger(Protocol):
    def credit(
        self,
        session: Session,
        project: uuid.UUID,
        player: uuid.UUID,
        currency: str,
        amount: int,
    ) -> Credited:
        """Add to a balance, in `session`'s transaction.

        Must neither commit nor roll back: the caller owns the transaction, and that is the
        whole point of the port. Raises `CurrencyRefused` for anything a request can cause."""
        ...


_ledger: CurrencyLedger | None = None


def provide(ledger: CurrencyLedger | None) -> None:
    """Called by the app that holds currency when it is imported. `None` withdraws it."""
    global _ledger
    _ledger = ledger


def provided() -> CurrencyLedger | None:
    return _ledger
