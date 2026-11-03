"""What the inventory needs from storage and from a schema validator, said as interfaces.

There is no in-memory implementation of storage. The rules the storage port exists to keep —
an item and its holders in the same project, nobody below zero, all of a grant or none of it —
are kept by PostgreSQL, and a fake would be a second implementation of exactly those rules,
passing tests the real one might fail.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from ..domain.attribute_schema import AttributeSchema
from ..domain.errors import Violation
from ..domain.grant import GrantLine
from ..domain.item import InventoryEntry, Item, ItemDraft


class Catalogue(Protocol):
    """The items one project defines, and the schema their attributes answer to."""

    def items(self) -> Sequence[Item]:
        """Every item, by id."""

    def find(self, item_id: str) -> Item | None: ...

    def save(self, draft: ItemDraft) -> Item:
        """Create or replace. A replacement keeps the item's creation time.

        Raises `Rejected` when the store cannot hold what the draft says."""

    def delete(self, item_id: str) -> bool:
        """True when there was such an item. Every inventory loses it too."""

    def schema_text(self) -> str | None:
        """The project's schema exactly as it was set, or None when it never declared one."""

    def replace_schema(self, schema: AttributeSchema) -> str:
        """Store the schema's text, and return it as stored."""


class Inventories(Protocol):
    """What the players of one project hold."""

    def of(self, player: uuid.UUID) -> Sequence[InventoryEntry]:
        """Every item this player holds, by item id, including any they hold none of now.
        Empty for a player with nothing, and for a player who is not there."""

    def grant(self, player: uuid.UUID, lines: Sequence[GrantLine]) -> Sequence[InventoryEntry]:
        """Apply every line or none of them, and return what the player then holds.

        Raises `NoSuchPlayer` when the player is not in this project, and `Rejected` naming
        every line that could not be applied — an unknown item, more taken than is held, or a
        total too large to store."""


class SchemaValidator(Protocol):
    """A JSON Schema implementation, held at arm's length.

    Behind a port because it is the one part of this app most likely to be swapped, and the
    part whose defaults are most dangerous: the library this service uses fetches remote
    references unless it is told not to.
    """

    def require_usable(self, schema: AttributeSchema) -> None:
        """Raise `Rejected`, at pointers into the schema, unless it can validate documents."""

    def violations(self, schema_text: str, document: Any) -> list[Violation]:
        """Every way `document` fails the schema, at pointers into the document, in pointer
        order. The schema is the stored text: a schema written past this service may not be
        one, and finding that out is this method's job, reported as `SchemaUnusable`."""
