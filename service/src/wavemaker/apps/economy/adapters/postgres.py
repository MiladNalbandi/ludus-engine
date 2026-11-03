"""Balances in PostgreSQL, each change one statement with the arithmetic inside it.

**Never read-modify-write.** Loading a balance, adding in Python and writing it back loses
updates: two grants arriving together both read 100, both write 101, and one is simply gone.
Nothing fails and nobody is told. The arithmetic happens in the database, in the statement that
writes it, so the row lock orders concurrent changes and each one sees the last.

**The first grant is the same single statement.** The Java got the arithmetic right and lost
grants anyway, one layer up: on a player's first grant, several threads found no row to
update, all inserted, one won, and the losers were reported as refused — two coins of twenty,
gone. Here a grant is `insert ... on conflict do update`, which PostgreSQL guarantees either
inserts or updates, atomically, whoever else is trying. There is no "no row yet" branch to get
wrong.

**The overdraft is the schema's to refuse.** A spend subtracts and lets the CHECK constraint
say no. It does not read the balance first, because a check-then-act is two statements with a
gap between them that a concurrent spend fits into exactly.

**Nor does a grant look the player up first.** The composite foreign key refuses a player who
is not in this project, in the same statement, with no gap for a delete to fall into. A player
who *is* in another project, and already holds that currency there, is caught by the upsert's
own `where`: the conflict target is (player_id, currency), so without it a grant from one
project would add to another's balance.

**A grant from another app is the same statement.** `PostgresLedger` is what this app provides
to the platform's currency port, so a reward can credit coins in its own transaction. It runs
the grant's upsert on the session it is handed and does not commit: the wallet route and the
ledger share one statement, so there is one place for its arithmetic and its project filter.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from wavemaker.apps.economy.domain.wallet import (
    Balance,
    InvalidRequest,
    NoSuchPlayer,
    NotEnough,
    TooLarge,
    currency_code,
    positive_amount,
)
from wavemaker.platform.currency import Credited, CurrencyRefused

FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
NUMERIC_OUT_OF_RANGE = "22003"


class PostgresWallets:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def balances(self, player: uuid.UUID) -> Sequence[Balance]:
        rows = self._session.execute(
            text("""
                select currency, amount, updated_at from economy_balance
                where project_id = :project and player_id = :player
                order by currency
            """),
            {"project": self._project, "player": player},
        ).all()
        return [_balance(row) for row in rows]

    def grant(self, player: uuid.UUID, currency: str, amount: int) -> Balance:
        try:
            row = _credit(self._session, self._project, player, currency, amount)
            self._session.commit()
        except DBAPIError as refused:
            self._session.rollback()
            state = _sqlstate(refused)
            if state == FOREIGN_KEY_VIOLATION:
                raise NoSuchPlayer("There is no such player in this project.") from refused
            if state == NUMERIC_OUT_OF_RANGE:
                raise TooLarge(f"/amount: {_too_large(currency)}") from refused
            raise
        if row is None:
            # It conflicted with a row the project filter excluded: this player exists, in
            # another project. From here that is the same as not existing at all.
            raise NoSuchPlayer("There is no such player in this project.")
        return _balance(row)

    def spend(self, player: uuid.UUID, currency: str, amount: int) -> Balance:
        try:
            row = self._session.execute(
                text("""
                    update economy_balance
                        set amount = amount - :amount,
                            updated_at = :now
                    where project_id = :project and player_id = :player and currency = :currency
                    returning currency, amount, updated_at
                """),
                self._parameters(player, currency, amount),
            ).one_or_none()
            self._session.commit()
        except DBAPIError as refused:
            self._session.rollback()
            if _sqlstate(refused) == CHECK_VIOLATION:
                raise NotEnough(f"/amount: not enough {currency} to spend {amount}.") from refused
            raise
        if row is None:
            # No balance at all. A spend from nothing is a refusal, not a first debit.
            raise NotEnough(f"/amount: not enough {currency} to spend {amount}.")
        return _balance(row)

    def _parameters(self, player: uuid.UUID, currency: str, amount: int) -> dict[str, Any]:
        return {
            "project": self._project,
            "player": player,
            "currency": currency,
            "amount": amount,
            "now": datetime.now(UTC),
        }


class PostgresLedger:
    """The economy's side of the platform's currency port: a grant inside a caller's own
    transaction, so a reward's coins and its XP are kept or lost together.

    The same statement as `PostgresWallets.grant`, and the same rules, because it is a second
    way into the same balances. What differs is that it never commits or rolls back. The caller
    owns the transaction; a refusal here is raised as `CurrencyRefused` and the caller rolls
    back everything it wrote, this credit included.

    A database refusal leaves the caller's transaction failed, so nothing more can be done in it
    but roll back — which is what a refused reward does anyway.
    """

    def credit(
        self,
        session: Session,
        project: uuid.UUID,
        player: uuid.UUID,
        currency: str,
        amount: int,
    ) -> Credited:
        try:
            code, amount = currency_code(currency), positive_amount(amount)
        except InvalidRequest as invalid:
            # The caller names the place; the field inside a grant is said in words.
            raise CurrencyRefused(str(invalid).removeprefix(f"{invalid.pointer}: ")) from invalid
        try:
            row = _credit(session, project, player, code, amount)
        except DBAPIError as refused:
            state = _sqlstate(refused)
            if state == FOREIGN_KEY_VIOLATION:
                raise CurrencyRefused("there is no such player in this project") from refused
            if state == NUMERIC_OUT_OF_RANGE:
                raise CurrencyRefused(_too_large(code)) from refused
            raise
        if row is None:
            # A player of another project, holding this currency there: see `_credit`.
            raise CurrencyRefused("there is no such player in this project")
        return Credited(currency=row.currency, amount=int(row.amount), updated_at=row.updated_at)


def _credit(
    session: Session, project: uuid.UUID, player: uuid.UUID, currency: str, amount: int
) -> Any:
    """Add `amount` to a balance, creating it on the first grant, in one statement. Neither
    commits nor rolls back. The row it leaves, or None when the player is another project's."""
    return session.execute(
        text("""
            insert into economy_balance as balance
                (project_id, player_id, currency, amount, updated_at)
            values (:project, :player, :currency, :amount, :now)
            on conflict (player_id, currency) do update
                set amount = balance.amount + excluded.amount,
                    updated_at = excluded.updated_at
                -- The key is (player_id, currency), so the row this conflicts with
                -- may be another project's. Without this the grant would add to it.
                where balance.project_id = excluded.project_id
            returning currency, amount, updated_at
        """),
        {
            "project": project,
            "player": player,
            "currency": currency,
            "amount": amount,
            "now": datetime.now(UTC),
        },
    ).one_or_none()


def _too_large(currency: str) -> str:
    return f"that would take the {currency} balance past the largest one that can be stored."


def _sqlstate(error: DBAPIError) -> str | None:
    state = getattr(error.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


def _balance(row: Any) -> Balance:
    return Balance(currency=row.currency, amount=int(row.amount), updated_at=row.updated_at)
