"""XP and the curve, in PostgreSQL.

**An award is one statement with the arithmetic inside it**, an upsert on (project, player),
for the wallet's reason: a first award has no row to update, and find-then-insert races there.

**A reward is one transaction.** The XP and every currency credit share this session, and a
refusal anywhere rolls all of it back. The currency ledger is handed the session and must not
commit; that is the contract of the platform's port.

**Replacing the curve takes a lock first.** It is a delete and an insert, and two of them at
once under read committed do not serialise by themselves: the second delete cannot see the rows
the first inserted, so its own insert collides with them and fails as a unique violation — a
500 for two editors pressing save together. A transaction-scoped advisory lock, keyed by the
project, makes the second wait for the first and then replace its curve whole.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from wavemaker.apps.progression.domain.curve import (
    Grant,
    NoSuchPlayer,
    ProgressionError,
    Rejected,
    Stage,
    TooMuchXp,
)
from wavemaker.platform.currency import Credited, CurrencyLedger, CurrencyRefused
from wavemaker.platform.identity import players

FOREIGN_KEY_VIOLATION = "23503"
NUMERIC_OUT_OF_RANGE = "22003"


class PostgresProgression:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def curve(self) -> list[Stage]:
        rows = self._session.execute(
            text("""
                select stage, xp_required, label from progression_stage
                where project_id = :project order by stage
            """),
            {"project": self._project},
        ).all()
        return [_row(row) for row in rows]

    def replace_curve(self, stages: Sequence[Stage]) -> list[Stage]:
        try:
            self._session.execute(
                text("select pg_advisory_xact_lock(hashtext('progression_stage:' || :project))"),
                {"project": str(self._project)},
            )
            self._session.execute(
                text("delete from progression_stage where project_id = :project"),
                {"project": self._project},
            )
            if stages:
                self._session.execute(
                    text("""
                        insert into progression_stage (project_id, stage, xp_required, label)
                        values (:project, :stage, :xp_required, :label)
                    """),
                    [
                        {
                            "project": self._project,
                            "stage": stage.stage,
                            "xp_required": stage.xp_required,
                            "label": stage.label,
                        }
                        for stage in stages
                    ],
                )
            stored = self.curve()
            self._session.commit()
        except BaseException:
            self._session.rollback()
            raise
        return stored

    def xp(self, player: uuid.UUID) -> int:
        found = self._session.execute(
            text("""
                select xp from progression_xp where project_id = :project and player_id = :player
            """),
            {"project": self._project, "player": player},
        ).scalar_one_or_none()
        return 0 if found is None else int(found)

    def reward(
        self,
        player: uuid.UUID,
        xp: int,
        grants: Sequence[Grant],
        ledger: CurrencyLedger | None,
    ) -> tuple[list[Credited], int]:
        try:
            if players.find(self._session, self._project, player) is None:
                raise NoSuchPlayer("There is no such player in this project.")
            total = self._award(player, xp) if xp > 0 else self.xp(player)
            balances = [
                self._credit(ledger, player, index, grant) for index, grant in enumerate(grants)
            ]
            self._session.commit()
        except DBAPIError as refused:
            self._session.rollback()
            state = _sqlstate(refused)
            if state == FOREIGN_KEY_VIOLATION:
                raise NoSuchPlayer("There is no such player in this project.") from refused
            if state == NUMERIC_OUT_OF_RANGE:
                raise TooMuchXp(
                    "/xp: that would take the player's XP past the most that can be stored"
                ) from refused
            raise
        except BaseException:
            # Every refusal, including one from the ledger, takes the whole reward with it.
            self._session.rollback()
            raise
        return balances, total

    def _award(self, player: uuid.UUID, xp: int) -> int:
        total = self._session.execute(
            text("""
                insert into progression_xp as progress (project_id, player_id, xp, updated_at)
                values (:project, :player, :xp, :now)
                on conflict (project_id, player_id) do update
                    set xp = progress.xp + excluded.xp,
                        updated_at = excluded.updated_at
                returning xp
            """),
            {"project": self._project, "player": player, "xp": xp, "now": datetime.now(UTC)},
        ).scalar_one()
        return int(total)

    def _credit(
        self, ledger: CurrencyLedger | None, player: uuid.UUID, index: int, grant: Grant
    ) -> Credited:
        if ledger is None:
            raise ProgressionError("a reward with currency reached storage with no ledger")
        try:
            return ledger.credit(self._session, self._project, player, grant.currency, grant.amount)
        except CurrencyRefused as refused:
            raise Rejected([f"/grants/{index}: {refused}"]) from refused


def _sqlstate(error: DBAPIError) -> str | None:
    state = getattr(error.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


def _row(row: Any) -> Stage:
    return Stage(int(row.stage), int(row.xp_required), row.label)
