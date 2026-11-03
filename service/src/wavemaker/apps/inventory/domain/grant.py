"""A grant: several items given or taken together, and what each line of one must be.

What is deliberately *not* here is whether a player holds enough to give something up, or
whether an item exists. Both are answered by the database in the statement that changes the
row — a check made here first would be a read with a gap after it, and a concurrent grant fits
in the gap exactly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import Rejected, Violation, rejected
from .item import MAX_ID_LENGTH, is_slug

# The largest quantity a bigint holds. A request for more cannot be stored, and saying so is
# better than letting the driver turn it into a numeric the column then refuses.
MAX_QUANTITY = 2**63 - 1

# One grant is one transaction holding a row lock per line. A loot table is a handful of
# lines; a thousand is a batch job, and a batch job should not hold locks on one request.
MAX_LINES = 100


@dataclass(frozen=True, slots=True)
class GrantLine:
    """An item and how many to add. Negative takes them away."""

    item_id: str
    quantity: int


def lines_of(body: Mapping[str, Any]) -> list[GrantLine]:
    """The lines of an `InventoryGrantRequest`, or every problem with them at its pointer."""
    items = body.get("items")
    if not isinstance(items, list) or not items:
        # A grant of nothing changes nothing, which makes it a client bug, like a quantity of 0.
        raise rejected("/items", "a grant is a list of at least one line")
    if len(items) > MAX_LINES:
        raise rejected("/items", f"a grant is at most {MAX_LINES} lines")

    found: list[Violation] = []
    lines: list[GrantLine] = []
    for index, line in enumerate(items):
        where = f"/items/{index}"
        if not isinstance(line, dict):
            found.append(Violation(where, "a line is an object with an itemId and a quantity"))
            continue
        item_id = line.get("itemId")
        quantity = line.get("quantity")
        if not is_slug(item_id, MAX_ID_LENGTH):
            found.append(Violation(f"{where}/itemId", f"{item_id!r} is not an item id"))
        problem = _quantity_problem(quantity)
        if problem:
            found.append(Violation(f"{where}/quantity", problem))
        if is_slug(item_id, MAX_ID_LENGTH) and isinstance(quantity, int) and not problem:
            lines.append(GrantLine(item_id=item_id, quantity=quantity))
    if found:
        raise Rejected(found)
    return lines


def _quantity_problem(value: object) -> str | None:
    """Why `value` is not a quantity, or None.

    `bool` is refused although Python calls it an int: `{"quantity": true}` is not one sword,
    it is a client bug, and accepting it would hide one. Zero is refused because it changes
    nothing, so whoever sent it meant something else.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return "a quantity is a whole number; negative takes items away"
    if value == 0:
        return "a grant of zero changes nothing; send a quantity"
    if abs(value) > MAX_QUANTITY:
        return f"a quantity is at most {MAX_QUANTITY} either way"
    return None
