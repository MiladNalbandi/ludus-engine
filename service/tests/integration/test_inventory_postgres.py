"""AC-2, AC-6, AC-8 and AC-9: the inventory rules, held by the schema and by one statement.

Every rule here is tested by doing the wrong thing straight to the database, past the
application, and watching it refuse. A rule that only holds when the caller is this application
is a rule the next code path, written later by somebody else, does not get.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TypeVar

import pytest
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from wavemaker.apps.inventory.adapters.postgres import PostgresCatalogue, PostgresInventories
from wavemaker.apps.inventory.domain.errors import NoSuchPlayer, Rejected
from wavemaker.apps.inventory.domain.grant import GrantLine
from wavemaker.apps.inventory.domain.item import InventoryEntry, draft_of
from wavemaker.platform.identity import players
from wavemaker.platform.persistence.engine import create_session_factory
from wavemaker.platform.tenancy import ensure_project

World = tuple[Session, uuid.UUID, uuid.UUID]


def define(session: Session, project: uuid.UUID, item_id: str, attributes: str = "{}") -> None:
    draft = draft_of(
        item_id, {"name": item_id.title(), "itemType": "thing", "attributes": attributes}
    )
    PostgresCatalogue(session, project).save(draft)


@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> Iterator[World]:
    """A project with one player and two items in it, and an open session."""
    with session_factory() as session:
        project = ensure_project(session, "inventory_rules", "Inventory rules")
        someone = players.start(session, project, "device-0001")
        define(session, project, "sword")
        define(session, project, "arrow")
        yield session, project, someone.id


def quantities(entries: object) -> dict[str, int]:
    assert isinstance(entries, list | tuple)
    return {entry.item_id: entry.quantity for entry in entries if isinstance(entry, InventoryEntry)}


# --- AC-2: the text, and the jsonb beside it ----------------------------------------------------


def test_ac2_the_text_is_kept_and_the_jsonb_is_generated_from_it(world: World) -> None:
    session, project, _ = world
    sent = '{ "damage": 12.0, "b": 1, "a": [1, 2.50] }'
    define(session, project, "bow", sent)

    stored, generated = session.execute(
        text("select attributes_json, attributes from inventory_item where item_id = 'bow'")
    ).one()
    assert stored == sent
    assert generated == json.loads(sent)

    # The column is for queries, and is indexed for them.
    found = (
        session.execute(text("select item_id from inventory_item where attributes @> '{\"b\": 1}'"))
        .scalars()
        .all()
    )
    assert found == ["bow"]


@pytest.mark.parametrize("attributes", ["[1, 2]", "12", "null"])
def test_ac2_the_table_itself_refuses_attributes_that_are_not_an_object(
    world: World, attributes: str
) -> None:
    session, project, _ = world
    with pytest.raises(IntegrityError, match="ck_inventory_item_attributes_object"):
        session.execute(
            text("""
                insert into inventory_item
                    (project_id, item_id, name, item_type, attributes_json, created_at, updated_at)
                values (:project, 'odd', 'Odd', 'thing', :attributes, now(), now())
            """),
            {"project": project, "attributes": attributes},
        )
    session.rollback()


def test_ac2_a_document_postgres_cannot_hold_is_a_refusal_not_an_error(world: World) -> None:
    """Python reads 1e-1000000 as 0.0. PostgreSQL's numeric cannot hold it, and says so in a
    data exception, which the adapter turns into a refusal at /attributes."""
    session, project, _ = world
    with pytest.raises(Rejected) as problem:
        define(session, project, "tiny", '{"weight": 1e-1000000}')
    assert problem.value.violations[0].pointer == "/attributes"
    assert PostgresCatalogue(session, project).find("tiny") is None


# --- AC-6: below zero, and all or nothing -------------------------------------------------------


def test_ac6_the_database_refuses_a_negative_quantity_whoever_asks(world: World) -> None:
    session, project, someone = world
    PostgresInventories(session, project).grant(someone, [GrantLine("arrow", 2)])

    with pytest.raises(IntegrityError, match="ck_inventory_entry_not_negative"):
        session.execute(text("update inventory_entry set quantity = quantity - 3"))
    session.rollback()


def test_ac6_a_refused_line_rolls_back_the_lines_before_it(world: World) -> None:
    session, project, someone = world
    inventories = PostgresInventories(session, project)
    with pytest.raises(Rejected) as problem:
        inventories.grant(
            someone, [GrantLine("sword", 1), GrantLine("arrow", -1), GrantLine("dragon", 1)]
        )
    assert [v.pointer for v in problem.value.violations] == [
        "/items/1/quantity",
        "/items/2/itemId",
    ]
    assert inventories.of(someone) == []
    assert session.execute(text("select count(*) from inventory_entry")).scalar_one() == 0


def test_ac6_a_change_is_one_statement_with_the_arithmetic_in_it(world: World) -> None:
    """No read of the quantity before the write: the gap between them is where a concurrent
    grant fits."""
    session, project, someone = world
    engine = session.get_bind()
    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]).strip().lower())

    event.listen(engine, "before_cursor_execute", record)
    try:
        PostgresInventories(session, project).grant(someone, [GrantLine("arrow", 5)])
    finally:
        event.remove(engine, "before_cursor_execute", record)

    changes = [s for s in statements if "inventory_entry" in s and not s.startswith("select")]
    assert len(changes) == 1
    assert "on conflict" in changes[0]
    assert "entry.quantity + excluded.quantity" in changes[0]
    reads_before = statements[: statements.index(changes[0])]
    assert not any("from inventory_entry" in s for s in reads_before)


def test_ac6_a_grant_to_a_player_of_another_project_is_no_such_player(
    session_factory: sessionmaker[Session], world: World
) -> None:
    session, project, someone = world
    PostgresInventories(session, project).grant(someone, [GrantLine("arrow", 5)])

    other = ensure_project(session, "other_game", "Other game")
    define(session, other, "arrow")
    with pytest.raises(NoSuchPlayer):
        PostgresInventories(session, other).grant(someone, [GrantLine("arrow", 1)])
    assert quantities(PostgresInventories(session, project).of(someone)) == {"arrow": 5}
    assert PostgresInventories(session, other).of(someone) == []


# --- AC-9: every row belongs to one project, and goes with what it belongs to ---------------------


@pytest.mark.parametrize("table", ["inventory_item_schema", "inventory_item", "inventory_entry"])
def test_ac9_every_new_table_belongs_to_a_project(
    session_factory: sessionmaker[Session], table: str
) -> None:
    with session_factory() as session:
        references = session.execute(
            text("""
                select confrelid::regclass::text as target, a.attname as column_name
                from pg_constraint c
                join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
                where c.contype = 'f' and c.conrelid = cast(:table as regclass)
                  and array_length(c.conkey, 1) = 1
            """),
            {"table": table},
        ).all()
        nullable = session.execute(
            text("""
                select is_nullable from information_schema.columns
                where table_name = :table and column_name = 'project_id'
            """),
            {"table": table},
        ).scalar_one()

    assert ("project", "project_id") in [(r.target, r.column_name) for r in references]
    assert nullable == "NO"


def test_ac9_a_row_cannot_pair_a_player_with_another_projects_item(world: World) -> None:
    """Both foreign keys are composite with the project, so the pairing is not insertable,
    whichever project the row claims."""
    session, project, someone = world
    other = ensure_project(session, "other_game", "Other game")
    define(session, other, "relic")

    for claimed in (project, other):
        with pytest.raises(IntegrityError, match="fk_inventory_entry"):
            session.execute(
                text("""
                    insert into inventory_entry
                        (project_id, player_id, item_id, quantity, updated_at)
                    values (:project, :player, 'relic', 1, now())
                """),
                {"project": claimed, "player": someone},
            )
        session.rollback()


def test_ac9_removing_a_player_or_an_item_removes_their_rows(world: World) -> None:
    session, project, someone = world
    second = players.start(session, project, "device-0002").id
    inventories = PostgresInventories(session, project)
    inventories.grant(someone, [GrantLine("sword", 1), GrantLine("arrow", 3)])
    inventories.grant(second, [GrantLine("sword", 1)])

    deleted = PostgresCatalogue(session, project).delete("sword")
    assert deleted
    assert quantities(inventories.of(someone)) == {"arrow": 3}
    assert inventories.of(second) == []

    session.execute(text("delete from player where id = :id"), {"id": someone})
    session.commit()
    assert session.execute(text("select count(*) from inventory_entry")).scalar_one() == 0


def test_ac9_a_schema_past_the_size_limit_cannot_be_written_even_past_the_service(
    world: World,
) -> None:
    session, project, _ = world
    with pytest.raises(DBAPIError, match="ck_inventory_item_schema_size"):
        session.execute(
            text("""
                insert into inventory_item_schema (project_id, schema_json, updated_at)
                values (:project, :schema, :now)
            """),
            {"project": project, "schema": "x" * 65537, "now": datetime.now(UTC)},
        )
    session.rollback()


# --- AC-8: concurrent first grants ----------------------------------------------------------------

THREADS = 20


@pytest.fixture
def engine(isolated_database_url: str) -> Iterator[Engine]:
    """One connection per thread, in a database of the test's own: the workers' rows are
    committed and nothing can roll them back."""
    created = create_engine(isolated_database_url, pool_size=THREADS, max_overflow=0)
    yield created
    created.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


# A classic TypeVar rather than `def all_at_once[T]`: CodeQL does not read the 3.12 syntax and
# reports `T` in the nested function as an uninitialised local.
T = TypeVar("T")


def all_at_once(  # noqa: UP047 - the TypeVar above, kept for CodeQL
    factory: sessionmaker[Session], work: Callable[[Session], T]
) -> list[T | Exception]:
    gate = threading.Barrier(THREADS)

    def one(_: int) -> T | Exception:
        with factory() as session:
            session.connection()
            gate.wait()
            try:
                return work(session)
            except Exception as failed:
                return failed

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(one, range(THREADS)))


def test_ac8_twenty_concurrent_first_grants_of_one_arrow_make_twenty(
    factory: sessionmaker[Session],
) -> None:
    """A player with no row for the item at all, so every thread races to create it. The
    Java's inventory took the same update-then-insert path its wallet lost grants on."""
    with factory() as session:
        project = ensure_project(session, "concurrency", "Concurrency")
        someone = players.start(session, project, "device-0001").id
        define(session, project, "arrow")

    results = all_at_once(
        factory,
        lambda session: PostgresInventories(session, project).grant(
            someone, [GrantLine("arrow", 1)]
        ),
    )

    refused = [result for result in results if isinstance(result, Exception)]
    assert refused == [], "no grant may be told it was refused"
    reported = sorted(quantities(result)["arrow"] for result in results)
    assert reported == list(range(1, THREADS + 1)), "each grant saw its own increment"
    with factory() as session:
        assert quantities(PostgresInventories(session, project).of(someone)) == {"arrow": THREADS}


def test_ac8_twenty_concurrent_takes_of_one_from_ten_let_exactly_ten_through(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        project = ensure_project(session, "concurrency", "Concurrency")
        someone = players.start(session, project, "device-0001").id
        define(session, project, "arrow")
        PostgresInventories(session, project).grant(someone, [GrantLine("arrow", 10)])

    results = all_at_once(
        factory,
        lambda session: PostgresInventories(session, project).grant(
            someone, [GrantLine("arrow", -1)]
        ),
    )

    taken = [result for result in results if not isinstance(result, Exception)]
    refused = [result for result in results if isinstance(result, Rejected)]
    unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, Rejected)]
    assert unexpected == [], "going below zero is a refusal, never an error"
    assert len(taken) == 10
    assert len(refused) == 10
    with factory() as session:
        assert quantities(PostgresInventories(session, project).of(someone)) == {"arrow": 0}
