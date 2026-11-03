"""AC-6, AC-7 and AC-9: the wallet rules, held by the schema and by the shape of one statement.

Every rule here is tested by doing the wrong thing straight to the database, past the
application, and watching it refuse. A rule that only holds when the caller is this
application is a rule the next code path, written later by somebody else, does not get.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from wavemaker.apps.economy.adapters.postgres import PostgresWallets
from wavemaker.apps.economy.domain.wallet import NoSuchPlayer, NotEnough
from wavemaker.platform.identity import players
from wavemaker.platform.tenancy import ensure_project


@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> Iterator[tuple[Session, uuid.UUID, uuid.UUID]]:
    """A project with one player in it, and an open session."""
    with session_factory() as session:
        project = ensure_project(session, "wallet_rules", "Wallet rules")
        someone = players.start(session, project, "device-0001")
        yield session, project, someone.id


def test_ac6_the_database_refuses_a_negative_balance_whoever_asks(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    """The overdraft guard is a CHECK constraint, so it holds for a code path that does not
    exist yet and forgets to check."""
    session, project, someone = world
    PostgresWallets(session, project).grant(someone, "coins", 10)

    with pytest.raises(IntegrityError, match="ck_economy_balance_not_negative"):
        session.execute(text("update economy_balance set amount = amount - 11"))
    session.rollback()

    with pytest.raises(IntegrityError, match="ck_economy_balance_not_negative"):
        session.execute(
            text("""
                insert into economy_balance (project_id, player_id, currency, amount, updated_at)
                values (:project, :player, 'gems', -1, now())
            """),
            {"project": project, "player": someone},
        )
    session.rollback()


def test_ac6_the_application_does_not_check_the_balance_first(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    """A spend is subtract-and-let-the-constraint-refuse, never read-then-decide. The gap
    between a read and a write is exactly where a concurrent spend fits."""
    session, project, someone = world
    wallets = PostgresWallets(session, project)
    wallets.grant(someone, "coins", 5)

    with recorded(session) as statements, pytest.raises(NotEnough):
        wallets.spend(someone, "coins", 6)

    assert len(statements) == 1, statements
    assert statements[0].lstrip().lower().startswith("update"), statements


def test_ac6_the_database_refuses_a_currency_code_that_is_not_one(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, project, someone = world
    with pytest.raises(IntegrityError, match="ck_economy_balance_currency"):
        session.execute(
            text("""
                insert into economy_balance (project_id, player_id, currency, amount, updated_at)
                values (:project, :player, 'Gold Coins', 1, now())
            """),
            {"project": project, "player": someone},
        )
    session.rollback()


@pytest.mark.parametrize("first", [True, False], ids=["first grant", "later grant"])
def test_ac7_a_grant_is_one_statement_with_the_arithmetic_in_it(
    world: tuple[Session, uuid.UUID, uuid.UUID], first: bool
) -> None:
    """Read-modify-write loses grants: two arrive together, both read 100, both write 101.
    One statement, with `amount + ...` inside it, cannot — including on the first grant,
    where there is no row to update yet."""
    session, project, someone = world
    wallets = PostgresWallets(session, project)
    if not first:
        wallets.grant(someone, "coins", 100)

    with recorded(session) as statements:
        balance = wallets.grant(someone, "coins", 1)

    assert balance.amount == (1 if first else 101)
    assert len(statements) == 1, statements
    assert "amount +" in " ".join(statements[0].split()), statements[0]


def test_ac7_a_spend_is_one_statement_with_the_arithmetic_in_it(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, project, someone = world
    wallets = PostgresWallets(session, project)
    wallets.grant(someone, "coins", 100)

    with recorded(session) as statements:
        assert wallets.spend(someone, "coins", 30).amount == 70

    assert len(statements) == 1, statements
    assert "amount -" in " ".join(statements[0].split()), statements[0]


def test_ac7_a_grant_to_a_player_who_is_not_there_is_refused_by_the_database(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    """By foreign key, not by a lookup first: no extra read, and no gap between the lookup and
    the write for a delete to fit into."""
    session, project, _ = world
    with pytest.raises(NoSuchPlayer):
        PostgresWallets(session, project).grant(uuid.uuid4(), "coins", 1)


def test_ac7_a_player_from_another_project_is_not_there(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        mine = ensure_project(session, "mine", "Mine")
        theirs = ensure_project(session, "theirs", "Theirs")
        someone = players.start(session, theirs, "device-0001")

        with pytest.raises(NoSuchPlayer):
            PostgresWallets(session, mine).grant(someone.id, "coins", 1)
        assert PostgresWallets(session, mine).balances(someone.id) == []

        # And once they hold some there, a grant from here must not add to it. The upsert
        # conflicts on (player, currency), which is their row, not ours.
        PostgresWallets(session, theirs).grant(someone.id, "coins", 10)
        with pytest.raises(NoSuchPlayer):
            PostgresWallets(session, mine).grant(someone.id, "coins", 1_000)
        assert [b.amount for b in PostgresWallets(session, theirs).balances(someone.id)] == [10]


def test_ac7_removing_a_player_takes_their_balances_with_them(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, project, someone = world
    PostgresWallets(session, project).grant(someone, "coins", 100)

    session.execute(text("delete from player where id = :id"), {"id": someone})
    session.commit()

    count = session.execute(text("select count(*) from economy_balance")).scalar_one()
    assert count == 0, "orphaned money is money nobody can see or spend"


@pytest.mark.parametrize("table", ["api_key", "player", "economy_balance"])
def test_ac9_every_new_table_belongs_to_a_project(
    session_factory: sessionmaker[Session], table: str
) -> None:
    """A tenant column added to a finished schema later means touching every table, key and
    query at once. Carrying it from the first migration costs one column."""
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


@contextmanager
def recorded(session: Session) -> Iterator[list[str]]:
    """Every statement a session sends while the block runs, minus transaction bookkeeping."""
    engine = session.get_bind()
    statements: list[str] = []

    def record(*args: Any) -> None:
        statement = str(args[2])
        if statement.strip().lower() not in ("begin", "commit", "rollback"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)
