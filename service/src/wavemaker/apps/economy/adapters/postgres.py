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
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from wavemaker.apps.economy.domain.wallet import Balance, NoSuchPlayer, NotEnough, TooLarge

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
            row = self._session.execute(
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
                self._parameters(player, currency, amount),
            ).one_or_none()
            self._session.commit()
        except DBAPIError as refused:
            self._session.rollback()
            state = _sqlstate(refused)
            if state == FOREIGN_KEY_VIOLATION:
                raise NoSuchPlayer("There is no such player in this project.") from refused
            if state == NUMERIC_OUT_OF_RANGE:
                raise TooLarge(
                    f"/amount: that would take the {currency} balance past the largest one "
                    "that can be stored."
                ) from refused
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


def _sqlstate(error: DBAPIError) -> str | None:
    state = getattr(error.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


def _balance(row: Any) -> Balance:
    return Balance(currency=row.currency, amount=int(row.amount), updated_at=row.updated_at)
