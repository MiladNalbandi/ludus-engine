"""Items and inventories in PostgreSQL.

**Documents are stored as the text that arrived**, with a `jsonb` column generated from it for
queries, exactly as a wave is. The attributes an editor wrote are what an editor reads back:
`2.0` stays `2.0` and the keys stay in their order.

**An inventory changes by one statement with the arithmetic inside it**, the same rule as a
wallet and for the same reason: an `insert ... on conflict do update` either inserts or adds,
atomically, whoever else is trying, so there is no "no row yet" branch for a concurrent first
grant to lose on. Taking more than a player holds is refused by the table's CHECK constraint,
not by a read beforehand that a concurrent grant could slip past.

**A grant is one transaction, with a savepoint per line.** A failed statement aborts a
PostgreSQL transaction, so without the savepoints the first bad line would hide every other
one. With them each line is tried, every refusal is collected, and then everything is rolled
back together if anything was refused: a player who received the sword and not the shield has
been given something the game never offered.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..domain.attribute_schema import AttributeSchema
from ..domain.errors import NoSuchPlayer, Rejected, Violation, rejected
from ..domain.grant import GrantLine
from ..domain.item import InventoryEntry, Item, ItemDraft

FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
NUMERIC_OUT_OF_RANGE = "22003"
# Class 22 is "data exception": a value PostgreSQL could not take, such as a number in the
# attributes too large for `jsonb` to hold.
DATA_EXCEPTION_CLASS = "22"

ITEM_COLUMNS = "item_id, name, item_type, sprite_ref, attributes_json, created_at, updated_at"


class PostgresCatalogue:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def items(self) -> Sequence[Item]:
        rows = self._session.execute(
            text(f"""
                select {ITEM_COLUMNS} from inventory_item
                where project_id = :project order by item_id
            """),
            {"project": self._project},
        ).all()
        return [_item(row) for row in rows]

    def find(self, item_id: str) -> Item | None:
        row = self._session.execute(
            text(f"""
                select {ITEM_COLUMNS} from inventory_item
                where project_id = :project and item_id = :item
            """),
            {"project": self._project, "item": item_id},
        ).one_or_none()
        return None if row is None else _item(row)

    def save(self, draft: ItemDraft) -> Item:
        """One upsert, so two editors saving a new item at once both succeed, the second as a
        replacement, rather than one being told the id is taken by an item it cannot see."""
        try:
            row = self._session.execute(
                text(f"""
                    insert into inventory_item as item
                        (project_id, item_id, name, item_type, sprite_ref, attributes_json,
                         created_at, updated_at)
                    values (:project, :item, :name, :item_type, :sprite_ref, :attributes,
                            :now, :now)
                    on conflict (project_id, item_id) do update
                        set name = excluded.name,
                            item_type = excluded.item_type,
                            sprite_ref = excluded.sprite_ref,
                            attributes_json = excluded.attributes_json,
                            updated_at = excluded.updated_at
                    returning {ITEM_COLUMNS}
                """),
                {
                    "project": self._project,
                    "item": draft.id,
                    "name": draft.name,
                    "item_type": draft.item_type,
                    "sprite_ref": draft.sprite_ref,
                    "attributes": draft.attributes,
                    "now": datetime.now(UTC),
                },
            ).one()
            self._session.commit()
        except DBAPIError as refused:
            self._session.rollback()
            state = _sqlstate(refused) or ""
            if state.startswith(DATA_EXCEPTION_CLASS):
                # Python read the document and PostgreSQL would not hold it: a number past
                # what `numeric` stores is the one known case. The caller's to fix, so a 422.
                raise rejected(
                    "/attributes", f"PostgreSQL cannot store this document: {_first_line(refused)}"
                ) from None
            raise
        return _item(row)

    def delete(self, item_id: str) -> bool:
        deleted = self._session.execute(
            text("delete from inventory_item where project_id = :project and item_id = :item"),
            {"project": self._project, "item": item_id},
        ).rowcount  # type: ignore[attr-defined]
        self._session.commit()
        return bool(deleted)

    def schema_text(self) -> str | None:
        stored: str | None = self._session.execute(
            text("select schema_json from inventory_item_schema where project_id = :project"),
            {"project": self._project},
        ).scalar_one_or_none()
        return stored

    def replace_schema(self, schema: AttributeSchema) -> str:
        self._session.execute(
            text("""
                insert into inventory_item_schema (project_id, schema_json, updated_at)
                values (:project, :schema, :now)
                on conflict (project_id) do update
                    set schema_json = excluded.schema_json, updated_at = excluded.updated_at
            """),
            {"project": self._project, "schema": schema.text, "now": datetime.now(UTC)},
        )
        self._session.commit()
        return schema.text


class PostgresInventories:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def of(self, player: uuid.UUID) -> Sequence[InventoryEntry]:
        rows = self._session.execute(
            text("""
                select item_id, quantity, updated_at from inventory_entry
                where project_id = :project and player_id = :player
                order by item_id
            """),
            {"project": self._project, "player": player},
        ).all()
        return [_entry(row) for row in rows]

    def grant(self, player: uuid.UUID, lines: Sequence[GrantLine]) -> Sequence[InventoryEntry]:
        try:
            # The player's row is held for the length of the grant, so it cannot be deleted
            # between this answer and the last line. `key share` is the weakest lock that does
            # that, and blocks nothing but a delete or a change of the player's id.
            present = self._session.execute(
                text("""
                    select 1 from player where id = :player and project_id = :project
                    for key share
                """),
                {"player": player, "project": self._project},
            ).one_or_none()
            if present is None:
                raise NoSuchPlayer("There is no such player in this project.")

            now = datetime.now(UTC)
            found = [
                problem
                for index, line in enumerate(lines)
                if (problem := self._apply(player, index, line, now)) is not None
            ]
            if found:
                raise Rejected(found)

            held = self.of(player)
            self._session.commit()
            return held
        except BaseException:
            self._session.rollback()
            raise

    def _apply(
        self, player: uuid.UUID, index: int, line: GrantLine, now: datetime
    ) -> Violation | None:
        """One line, inside its own savepoint. A refusal, or None when it applied."""
        parameters = {
            "project": self._project,
            "player": player,
            "item": line.item_id,
            "quantity": line.quantity,
            "now": now,
        }
        savepoint = self._session.begin_nested()
        try:
            changed = self._session.execute(
                text(GIVE if line.quantity > 0 else TAKE), parameters
            ).one_or_none()
            savepoint.commit()
        except DBAPIError as refused:
            savepoint.rollback()
            return _refusal(refused, index, line)
        if changed is None:
            # A take from a row that is not there. Which of two reasons is only a message, so
            # it is asked after the fact rather than checked before.
            return self._nothing_to_take(index, line)
        return None

    def _nothing_to_take(self, index: int, line: GrantLine) -> Violation:
        exists = self._session.execute(
            text("select 1 from inventory_item where project_id = :project and item_id = :item"),
            {"project": self._project, "item": line.item_id},
        ).one_or_none()
        if exists is None:
            return _no_such_item(index, line)
        return _not_enough(index, line)


# Giving is an upsert: one statement that inserts the first one or adds to the row that is
# there, atomically, whoever else is trying.
GIVE = """
    insert into inventory_entry as entry (project_id, player_id, item_id, quantity, updated_at)
    values (:project, :player, :item, :quantity, :now)
    on conflict (project_id, player_id, item_id) do update
        set quantity = entry.quantity + excluded.quantity,
            updated_at = excluded.updated_at
    returning quantity
"""

# Taking is an update and never an upsert. PostgreSQL checks a row's constraints *before* it
# looks for a conflict, so an upsert proposing quantity -1 is refused by the CHECK even when
# the row it would have added to holds ten. A take from no row at all is no take.
TAKE = """
    update inventory_entry
        set quantity = quantity + :quantity,
            updated_at = :now
    where project_id = :project and player_id = :player and item_id = :item
    returning quantity
"""


def _refusal(refused: DBAPIError, index: int, line: GrantLine) -> Violation:
    state = _sqlstate(refused)
    if state == CHECK_VIOLATION:
        return _not_enough(index, line)
    if state == FOREIGN_KEY_VIOLATION:
        # The player was locked above, so the only key that can be missing is the item's.
        return _no_such_item(index, line)
    if state == NUMERIC_OUT_OF_RANGE:
        return Violation(
            f"/items/{index}/quantity",
            f"that would take the player's '{line.item_id}' past the largest number that can "
            "be stored",
        )
    raise refused


def _not_enough(index: int, line: GrantLine) -> Violation:
    return Violation(
        f"/items/{index}/quantity",
        f"the player does not have {abs(line.quantity)} of '{line.item_id}'",
    )


def _no_such_item(index: int, line: GrantLine) -> Violation:
    return Violation(f"/items/{index}/itemId", f"no item '{line.item_id}' in this project")


def _sqlstate(error: DBAPIError) -> str | None:
    state = getattr(error.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


def _first_line(error: DBAPIError) -> str:
    return str(error.orig).splitlines()[0] if error.orig is not None else "refused"


def _item(row: Any) -> Item:
    return Item(
        id=row.item_id,
        name=row.name,
        item_type=row.item_type,
        sprite_ref=row.sprite_ref,
        attributes=row.attributes_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _entry(row: Any) -> InventoryEntry:
    return InventoryEntry(
        item_id=row.item_id, quantity=int(row.quantity), updated_at=row.updated_at
    )
