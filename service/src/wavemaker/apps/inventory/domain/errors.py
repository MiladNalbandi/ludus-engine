"""What the inventory refuses, said so that a client can show it where the problem is.

Every refusal a caller can cause carries a JSON Pointer into what they sent. "The item is
invalid" is not something an editor can fix; "/attributes/damage: -1 is less than the minimum
of 0" is, and an editor can highlight the field it names.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

from wavemaker.platform.kernel.errors import PlatformError

# A response listing a thousand violations helps nobody read it and costs whoever sends it.
# The first few, in pointer order, are enough to start fixing.
MAX_REPORTED = 20


class Violation(NamedTuple):
    """One problem, and where it is. An empty pointer is the whole document."""

    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer}: {self.message}" if self.pointer else self.message


class InventoryError(PlatformError):
    """A request about items that was understood and not acted on."""


class Rejected(InventoryError):
    """What was sent cannot be accepted as it stands. Every problem found, not only the first:
    correcting a document one round trip per problem is the slowest way there is."""

    def __init__(self, violations: Iterable[Violation]) -> None:
        self.violations = tuple(violations)
        if not self.violations:
            raise ValueError("a rejection names at least one problem")
        shown = [str(violation) for violation in self.violations[:MAX_REPORTED]]
        hidden = len(self.violations) - len(shown)
        if hidden:
            shown.append(f"and {hidden} more")
        super().__init__("; ".join(shown))


class NoSuchPlayer(InventoryError):
    """The player is not in this project, or was never anywhere."""


class SchemaUnusable(InventoryError):
    """A project's item schema that cannot be used to validate anything.

    Raised when a schema is set, so the project hears about it then rather than from the first
    editor who tries to save an item. A stored schema can only be unusable if it was written
    past this application, and that is reported as the project's problem, not the item's.
    """


def rejected(pointer: str, message: str) -> Rejected:
    return Rejected([Violation(pointer, message)])


def escape(token: str | int) -> str:
    """One JSON Pointer reference token (RFC 6901): `~` and `/` are the two that need it."""
    return str(token).replace("~", "~0").replace("/", "~1")


def pointer(*tokens: str | int) -> str:
    return "".join(f"/{escape(token)}" for token in tokens)
