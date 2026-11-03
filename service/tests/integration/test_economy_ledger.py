"""The economy's currency ledger: a grant made inside somebody else's transaction.

`rewardPlayer` is progression's, and the coins in a reward are the economy's. The platform's
currency port joins them, and the economy provides the ledger behind it. What the ledger owes
is narrow and each part is tested here against PostgreSQL: it credits with the wallet's own
single-statement upsert, it never commits, it stays inside its project, and everything a
request can cause comes back as `CurrencyRefused` rather than as a database error a caller
would have to recognise.
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.test_wallet_postgres import recorded
from wavemaker.apps.economy.adapters.postgres import PostgresWallets
from wavemaker.platform import currency
from wavemaker.platform.currency import CurrencyLedger, CurrencyRefused
from wavemaker.platform.identity import players
from wavemaker.platform.tenancy import ensure_project

MAX_BALANCE = 2**63 - 1


def economy_ledger() -> CurrencyLedger:
    """What the economy registers when it is loaded, as the service loads it."""
    importlib.import_module("wavemaker.apps.economy")
    provided = currency.provided()
    assert provided is not None, "loading the economy app provides no currency ledger"
    return provided


@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> Iterator[tuple[Session, uuid.UUID, uuid.UUID]]:
    with session_factory() as session:
        project = ensure_project(session, "ledger", "Ledger")
        someone = players.start(session, project, "device-0001")
        yield session, project, someone.id


def balance(session: Session, project: uuid.UUID, player: uuid.UUID, code: str) -> int | None:
    found = session.execute(
        text("""
            select amount from economy_balance
            where project_id = :project and player_id = :player and currency = :currency
        """),
        {"project": project, "player": player, "currency": code},
    ).scalar_one_or_none()
    return None if found is None else int(found)


def test_loading_the_economy_provides_a_ledger() -> None:
    ledger = economy_ledger()
    assert type(ledger).__module__.startswith("wavemaker.apps.economy")


@pytest.mark.parametrize("first", [True, False], ids=["first credit", "later credit"])
def test_a_credit_is_the_wallets_one_statement_upsert(
    world: tuple[Session, uuid.UUID, uuid.UUID], first: bool
) -> None:
    session, project, someone = world
    if not first:
        PostgresWallets(session, project).grant(someone, "coins", 100)

    with recorded(session) as statements:
        credited = economy_ledger().credit(session, project, someone, "coins", 1)

    assert (credited.currency, credited.amount) == ("coins", 1 if first else 101)
    assert len(statements) == 1, statements
    assert "amount +" in " ".join(statements[0].split()), statements[0]


def test_a_credit_does_not_commit(world: tuple[Session, uuid.UUID, uuid.UUID]) -> None:
    """The caller owns the transaction: that is the whole point of the port. A ledger that
    committed would make a reward's coins survive the XP being refused."""
    session, project, someone = world
    economy_ledger().credit(session, project, someone, "coins", 40)
    assert balance(session, project, someone, "coins") == 40, "visible inside the transaction"

    session.rollback()
    assert balance(session, project, someone, "coins") is None


def test_a_credit_the_caller_commits_is_kept(world: tuple[Session, uuid.UUID, uuid.UUID]) -> None:
    session, project, someone = world
    economy_ledger().credit(session, project, someone, "coins", 40)
    session.commit()
    assert [b.amount for b in PostgresWallets(session, project).balances(someone)] == [40]


def test_a_credit_past_the_largest_balance_is_refused_not_a_database_error(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, project, someone = world
    PostgresWallets(session, project).grant(someone, "coins", MAX_BALANCE)

    with pytest.raises(CurrencyRefused, match="coins"):
        economy_ledger().credit(session, project, someone, "coins", 1)
    session.rollback()
    assert balance(session, project, someone, "coins") == MAX_BALANCE


def test_a_credit_to_a_player_who_is_not_there_is_refused(
    world: tuple[Session, uuid.UUID, uuid.UUID],
) -> None:
    session, project, _ = world
    with pytest.raises(CurrencyRefused):
        economy_ledger().credit(session, project, uuid.uuid4(), "coins", 1)
    session.rollback()


def test_a_credit_cannot_add_to_another_projects_balance(
    session_factory: sessionmaker[Session],
) -> None:
    """The balance key is (player_id, currency), so a credit naming a player of another project
    conflicts with *their* row. The upsert's project filter is what keeps it from adding to it."""
    with session_factory() as session:
        mine = ensure_project(session, "mine", "Mine")
        theirs = ensure_project(session, "theirs", "Theirs")
        stranger = players.start(session, theirs, "device-0001").id
        PostgresWallets(session, theirs).grant(stranger, "coins", 10)

        with pytest.raises(CurrencyRefused):
            economy_ledger().credit(session, mine, stranger, "coins", 1_000)
        session.rollback()
        assert balance(session, theirs, stranger, "coins") == 10


@pytest.mark.parametrize(("code", "amount"), [("Gold Coins", 1), ("coins", 0), ("coins", True)])
def test_a_credit_the_wallet_would_not_accept_is_refused(
    world: tuple[Session, uuid.UUID, uuid.UUID], code: str, amount: int
) -> None:
    """The economy's own rules, not only the caller's: a ledger is a second way in, and it must
    not accept what the grant route refuses."""
    session, project, someone = world
    with pytest.raises(CurrencyRefused):
        economy_ledger().credit(session, project, someone, code, amount)
    session.rollback()
    assert PostgresWallets(session, project).balances(someone) == []
