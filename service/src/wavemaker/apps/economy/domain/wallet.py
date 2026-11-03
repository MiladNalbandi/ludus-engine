"""Balances, and what a request to change one must be.

What is here is the caller's side of the rules: a currency is the project's own word, and an
amount is a whole number above zero. What is deliberately *not* here is whether a player can
afford something. That is answered by the database, in the same statement that spends — a
check made here first would be a read with a gap after it, and a concurrent spend fits in the
gap exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# The project's own vocabulary: coins, gems, energy. Not an enum, because an enum would mean a
# release of this service every time a game invents a currency. The shape is the same one the
# schema checks, so a code is safe in a URL and as a JSON key without escaping.
CURRENCY = re.compile(r"^[a-z0-9_]+$")
MAX_CURRENCY_LENGTH = 40

# The largest balance a bigint holds. A request for more cannot be stored, and saying so is
# better than letting the driver turn it into a numeric the column then refuses.
MAX_AMOUNT = 2**63 - 1


@dataclass(frozen=True, slots=True)
class Balance:
    currency: str
    amount: int
    updated_at: datetime


class EconomyError(Exception):
    """A change to a wallet that was understood and not made."""


class InvalidRequest(EconomyError):
    """The request is not a change anybody could make. `pointer` names the field."""

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer


class NotEnough(EconomyError):
    """A spend the balance does not cover. Refused, never clamped to zero."""


class TooLarge(EconomyError):
    """A grant that would take a balance past what can be stored."""


class NoSuchPlayer(EconomyError):
    """The player is not in this project, or was never anywhere."""


def currency_code(value: object) -> str:
    if (
        not isinstance(value, str)
        or not CURRENCY.match(value)
        or len(value) > MAX_CURRENCY_LENGTH
    ):
        raise InvalidRequest(
            "/currency",
            f"a currency is lower-case letters, digits and '_', at most "
            f"{MAX_CURRENCY_LENGTH} characters",
        )
    return value


def positive_amount(value: object) -> int:
    """A whole number of at least one.

    `bool` is refused although Python calls it an int: `{"amount": true}` is not one coin, it
    is a client bug, and accepting it would hide one. Zero and negatives are refused too: a
    negative grant is a spend that skipped the player, and a negative spend is a grant a player
    gave themselves.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidRequest("/amount", "an amount is a whole number of at least 1")
    if value > MAX_AMOUNT:
        raise InvalidRequest("/amount", f"an amount is at most {MAX_AMOUNT}")
    return value
