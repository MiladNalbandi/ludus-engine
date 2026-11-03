"""Reading content out of PostgreSQL, behind the same port the in-memory one implements.

Every query filters on `project_id` and on `published`, and both filters live here rather than
in a route. "Which rows may a client see" is a storage question; a route that filtered them
itself is a route that can forget to, and the thing it forgets is unreleased content.

Documents come back out of `config_json`, never out of the generated `config` column. The text
column holds the bytes that were written; the jsonb column is derived from them and reorders
keys, so serving from it would change every client's ETag without any content changing.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wavemaker.apps.content.domain.document import OrderTaken, WaveDocument
from wavemaker.apps.content.domain.level import LevelDraft
from wavemaker.apps.content.domain.wave import (
    LevelMember,
    LevelSummary,
    MissingWaves,
    PlayableLevel,
    Rejected,
    WaveSummary,
)

# The schema every document written through this service is validated against.
SCHEMA_URI = "https://ludus.dev/schemas/wave/v1.json"

SUMMARY_COLUMNS = """
    wave_id, name, wave_order, schema_version, published, created_at, updated_at
"""


class PostgresWaveRepository:
    def __init__(self, session: Session, project_id: uuid.UUID) -> None:
        self._session = session
        self._project = project_id

    def published_catalogue(self) -> Sequence[WaveSummary]:
        rows = self._session.execute(
            text(f"""
                select {SUMMARY_COLUMNS} from wave
                where project_id = :project and published
                order by wave_order
            """),
            {"project": self._project},
        ).all()
        return [_summary(row) for row in rows]

    def find_published(self, wave_id: str) -> WaveSummary | None:
        row = self._session.execute(
            text(f"""
                select {SUMMARY_COLUMNS} from wave
                where project_id = :project and wave_id = :wave and published
            """),
            {"project": self._project, "wave": wave_id},
        ).one_or_none()
        return None if row is None else _summary(row)

    def published_document(self, wave_id: str) -> bytes | None:
        found = self._session.execute(
            text("""
                select config_json from wave
                where project_id = :project and wave_id = :wave and published
            """),
            {"project": self._project, "wave": wave_id},
        ).scalar_one_or_none()
        return None if found is None else str(found).encode()

    def published_documents(self, wave_ids: Sequence[str]) -> Mapping[str, bytes]:
        if not wave_ids:
            # `in ()` is not valid SQL, and an empty batch is a legitimate question with an
            # empty answer rather than an error.
            return {}

        rows = self._session.execute(
            text("""
                select wave_id, config_json from wave
                where project_id = :project and published and wave_id = any(:waves)
            """),
            {"project": self._project, "waves": list(wave_ids)},
        ).all()
        # Keyed by the order asked for, so a client gets its own ordering back rather than the
        # database's. Ids that are drafts or unknown are simply absent.
        found = {row.wave_id: str(row.config_json).encode() for row in rows}
        return {wave_id: found[wave_id] for wave_id in wave_ids if wave_id in found}

    def active_level(self) -> PlayableLevel | None:
        level = self._session.execute(
            text("""
                select id, name from wave_level
                where project_id = :project and active
            """),
            {"project": self._project},
        ).one_or_none()
        if level is None:
            return None

        # Every wave the level names, drafts included. Which of them a client may see is
        # decided when the level is served — a level that dropped its drafts here could never
        # tell an editor "2 of 3 reach players".
        wave_ids = (
            self._session.execute(
                text("""
                select wave_id from wave_level_wave
                where wave_level_id = :level and project_id = :project
                order by position
            """),
                {"level": level.id, "project": self._project},
            )
            .scalars()
            .all()
        )

        return PlayableLevel(id=str(level.id), name=level.name, wave_ids=list(wave_ids))

    # --- authoring ------------------------------------------------------------------------

    def all_summaries(self) -> Sequence[WaveSummary]:
        rows = self._session.execute(
            text(f"""
                select {SUMMARY_COLUMNS} from wave
                where project_id = :project
                order by wave_order
            """),
            {"project": self._project},
        ).all()
        return [_summary(row) for row in rows]

    def document(self, wave_id: str) -> bytes | None:
        """Any wave's bytes, published or not. The authoring counterpart of
        `published_document`: an author must be able to open a draft."""
        found = self._session.execute(
            text("select config_json from wave where project_id = :p and wave_id = :w"),
            {"p": self._project, "w": wave_id},
        ).scalar_one_or_none()
        return None if found is None else str(found).encode()

    def save(self, document: WaveDocument) -> WaveSummary:
        """Create or replace, without touching publication state.

        A save is not a publish. If saving re-published a withdrawn wave, the only way to fix a
        live wave would be to delete it.
        """
        now = datetime.now(UTC)
        try:
            self._session.execute(
                text("""
                    insert into wave (project_id, wave_id, schema_uri, schema_version, name,
                                      wave_order, config_json, created_at, updated_at)
                    values (:p, :w, :uri, :ver, :n, :o, :doc, :now, :now)
                    on conflict (project_id, wave_id) do update set
                        schema_version = excluded.schema_version,
                        name           = excluded.name,
                        wave_order     = excluded.wave_order,
                        config_json    = excluded.config_json,
                        updated_at     = excluded.updated_at
                """),
                {
                    "p": self._project,
                    "w": document.id,
                    "uri": SCHEMA_URI,
                    "ver": document.schema_version,
                    "n": document.name,
                    "o": document.order,
                    "doc": document.raw.decode(),
                    "now": now,
                },
            )
            self._session.commit()
        except IntegrityError as clash:
            self._session.rollback()
            if "uq_wave_order" in str(clash.orig):
                raise OrderTaken(
                    f"/progression_config/order: position {document.order} is already played by "
                    "another wave."
                ) from clash
            raise

        saved = self._session.execute(
            text(f"select {SUMMARY_COLUMNS} from wave where project_id = :p and wave_id = :w"),
            {"p": self._project, "w": document.id},
        ).one()
        return _summary(saved)

    def set_published(self, wave_id: str, published: bool) -> WaveSummary | None:
        # updated_at moves with it, so publishing changes the catalogue hash and every client
        # polling /status learns there is something new. Without that, publishing would be
        # invisible until something else happened to change.
        row = self._session.execute(
            text(f"""
                update wave set published = :pub, updated_at = :now
                where project_id = :p and wave_id = :w
                returning {SUMMARY_COLUMNS}
            """),
            {"pub": published, "now": datetime.now(UTC), "p": self._project, "w": wave_id},
        ).one_or_none()
        self._session.commit()
        return None if row is None else _summary(row)

    def delete(self, wave_id: str) -> bool:
        result = cast("CursorResult[Any]", self._session.execute(
            text("delete from wave where project_id = :p and wave_id = :w"),
            {"p": self._project, "w": wave_id},
        ))
        self._session.commit()
        return bool(result.rowcount)

    def next_order(self) -> int:
        highest = self._session.execute(
            text("select max(wave_order) from wave where project_id = :p"),
            {"p": self._project},
        ).scalar_one()
        return 0 if highest is None else int(highest) + 1

    def all_levels(self) -> Sequence[LevelSummary]:
        return self._levels(None)

    def level(self, level_id: str) -> LevelSummary | None:
        key = _level_key(level_id)
        if key is None:
            return None
        return next(iter(self._levels(key)), None)

    def create_level(self, draft: LevelDraft) -> LevelSummary:
        """A new level, inactive: making a level and choosing what players receive are two
        decisions, and an author building next week's level must not ship it by saving it."""
        key = uuid.uuid4()
        now = datetime.now(UTC)
        try:
            self._require_waves(draft.wave_ids)
            self._session.execute(
                text("""
                    insert into wave_level (id, project_id, name, description, active,
                                            created_at, updated_at)
                    values (:id, :p, :n, :d, false, :now, :now)
                """),
                {
                    "id": key,
                    "p": self._project,
                    "n": draft.name,
                    "d": draft.description,
                    "now": now,
                },
            )
            self._write_members(key, draft.wave_ids)
            # Read inside the transaction that wrote it, so the answer is this write and not
            # whatever somebody else did in the moment after it committed.
            created = self._levels(key)[0]
            self._session.commit()
        except IntegrityError as clash:
            raise self._refused(clash, draft.wave_ids) from clash
        except BaseException:
            self._session.rollback()
            raise
        return created

    def update_level(self, level_id: str, draft: LevelDraft) -> LevelSummary | None:
        """Rename and resequence in one transaction: the level ends with exactly the new list
        or exactly the old one.

        The level's own row is updated first, and that order is the behaviour. The update takes
        the row's lock, so a second replacement of the same level waits there until the first
        has committed, and its delete then sees the first one's members. Deleting members first
        instead lets two replacements both delete the old rows, both insert from position 0,
        and collide on the unique position: a 500 for an author whose request was fine.
        """
        key = _level_key(level_id)
        if key is None:
            return None
        try:
            touched = self._session.execute(
                text("""
                    update wave_level set name = :n, description = :d, updated_at = :now
                    where project_id = :p and id = :id
                    returning id
                """),
                {
                    "n": draft.name,
                    "d": draft.description,
                    "now": datetime.now(UTC),
                    "p": self._project,
                    "id": key,
                },
            ).one_or_none()
            if touched is None:
                self._session.rollback()
                return None

            self._require_waves(draft.wave_ids)
            # Replaced wholesale rather than diffed. Rewriting positions in place collides with
            # the unique position halfway through any reorder, which is how the Java's first
            # version of this broke.
            self._session.execute(
                text("delete from wave_level_wave where project_id = :p and wave_level_id = :id"),
                {"p": self._project, "id": key},
            )
            self._write_members(key, draft.wave_ids)
            updated = self._levels(key)[0]
            self._session.commit()
        except IntegrityError as clash:
            raise self._refused(clash, draft.wave_ids) from clash
        except BaseException:
            self._session.rollback()
            raise
        return updated

    def delete_level(self, level_id: str) -> bool:
        """The membership rows go with the level by foreign key, and the waves stay.

        Deleting the active level leaves none active, because "active" is a column on the row
        that went. Nothing promotes another level in its place: which one would be a guess, and
        a wrong guess ships a level to every player.
        """
        key = _level_key(level_id)
        if key is None:
            return False
        result = cast(
            "CursorResult[Any]",
            self._session.execute(
                text("delete from wave_level where project_id = :p and id = :id"),
                {"p": self._project, "id": key},
            ),
        )
        self._session.commit()
        return bool(result.rowcount)

    def activate_level(self, level_id: str) -> LevelSummary | None:
        key = _level_key(level_id)
        if key is None:
            return None
        # Stand every level down first. The partial unique index allows exactly one active
        # level, so setting the new one while the old is still active would be refused — the
        # constraint makes the order of these two statements part of the behaviour.
        self._session.execute(
            text("update wave_level set active = false where project_id = :p and active"),
            {"p": self._project},
        )
        changed = cast("CursorResult[Any]", self._session.execute(
            text("""
                update wave_level set active = true, updated_at = :now
                where project_id = :p and id = :id
            """),
            {"now": datetime.now(UTC), "p": self._project, "id": key},
        ))
        if not changed.rowcount:
            self._session.rollback()
            return None
        self._session.commit()
        return self.level(level_id)

    def delete_all(self, wave_ids: Sequence[str]) -> int:
        """One statement, then a look at what it removed: if any id named nothing, the whole
        delete is rolled back. The waves leave every level they were in, by foreign key."""
        try:
            gone = set(
                self._session.execute(
                    text("""
                        delete from wave where project_id = :p and wave_id = any(:w)
                        returning wave_id
                    """),
                    {"p": self._project, "w": list(wave_ids)},
                ).scalars()
            )
            missing = [(index, w) for index, w in enumerate(wave_ids) if w not in gone]
            if missing:
                raise MissingWaves("/ids", missing)
            self._session.commit()
        except BaseException:
            self._session.rollback()
            raise
        return len(gone)

    # --- levels, below the port ---------------------------------------------------------------

    def _levels(self, only: uuid.UUID | None) -> list[LevelSummary]:
        """Every level, or the one with this key, each with its members in order and whether
        each member is published now — read with the level, never copied into it."""
        levels = self._session.execute(
            text("""
                select id, name, description, active, created_at, updated_at from wave_level
                where project_id = :p and (cast(:id as uuid) is null or id = :id)
                order by name
            """),
            {"p": self._project, "id": only},
        ).all()

        members = self._session.execute(
            text("""
                select m.wave_level_id, m.wave_id, w.published
                from wave_level_wave m
                join wave w on w.project_id = m.project_id and w.wave_id = m.wave_id
                where m.project_id = :p
                  and (cast(:id as uuid) is null or m.wave_level_id = :id)
                order by m.position
            """),
            {"p": self._project, "id": only},
        ).all()

        by_level: dict[str, list[LevelMember]] = {}
        for row in members:
            by_level.setdefault(str(row.wave_level_id), []).append(
                LevelMember(wave_id=row.wave_id, published=row.published)
            )

        return [
            LevelSummary(
                id=str(level.id),
                name=level.name,
                description=level.description,
                active=level.active,
                waves=by_level.get(str(level.id), []),
                created_at=level.created_at,
                updated_at=level.updated_at,
            )
            for level in levels
        ]

    def _missing_waves(self, wave_ids: Sequence[str]) -> list[tuple[int, str]]:
        """Each listed id with no wave in this project, with its position.

        `for share` holds the waves that were found until the transaction ends, so none of them
        can be deleted between this check and the insert that relies on it. The composite
        foreign key would refuse that insert either way; the lock makes the refusal something
        that does not happen rather than something that is merely handled.
        """
        if not wave_ids:
            return []
        found = set(
            self._session.execute(
                text("""
                    select wave_id from wave
                    where project_id = :p and wave_id = any(:w)
                    for share
                """),
                {"p": self._project, "w": list(wave_ids)},
            ).scalars()
        )
        return [(index, w) for index, w in enumerate(wave_ids) if w not in found]

    def _require_waves(self, wave_ids: Sequence[str]) -> None:
        missing = self._missing_waves(wave_ids)
        if missing:
            raise MissingWaves("/waves", missing)

    def _write_members(self, key: uuid.UUID, wave_ids: Sequence[str]) -> None:
        """Every member in one statement, each at its index in the list."""
        if not wave_ids:
            return
        self._session.execute(
            text("""
                insert into wave_level_wave (project_id, wave_level_id, wave_id, position)
                select :p, :l, listed.wave_id, listed.position - 1
                from unnest(cast(:w as varchar[])) with ordinality as listed(wave_id, position)
            """),
            {"p": self._project, "l": key, "w": list(wave_ids)},
        )

    def _refused(self, clash: IntegrityError, wave_ids: Sequence[str]) -> Exception:
        """What to tell an author when the database refused a level's membership.

        Reached only when the checks in front of the database were missed. A foreign-key
        refusal names the missing waves when they can still be found; a violation that is not
        a membership rule is a real fault and goes up as it came.
        """
        self._session.rollback()
        rejection = membership_rejection(clash)
        if rejection is None:
            return clash
        if _constraint(clash) == "fk_wave_level_wave_wave":
            missing = self._missing_waves(wave_ids)
            self._session.rollback()
            if missing:
                return MissingWaves("/waves", missing)
        return rejection

    def save_all(self, documents: Sequence[WaveDocument]) -> Sequence[WaveSummary]:
        """Every document in one transaction, so a bad one leaves the catalogue untouched.

        `save` commits per wave, which is right for an author editing one. An import is a
        single decision, and half of one is worse than none of it.
        """
        now = datetime.now(UTC)
        try:
            for document in documents:
                self._session.execute(
                    text("""
                        insert into wave (project_id, wave_id, schema_uri, schema_version, name,
                                          wave_order, config_json, created_at, updated_at)
                        values (:p, :w, :uri, :ver, :n, :o, :doc, :now, :now)
                        on conflict (project_id, wave_id) do update set
                            schema_version = excluded.schema_version,
                            name           = excluded.name,
                            wave_order     = excluded.wave_order,
                            config_json    = excluded.config_json,
                            updated_at     = excluded.updated_at
                    """),
                    {
                        "p": self._project,
                        "w": document.id,
                        "uri": SCHEMA_URI,
                        "ver": document.schema_version,
                        "n": document.name,
                        "o": document.order,
                        "doc": document.raw.decode(),
                        "now": now,
                    },
                )
            self._session.commit()
        except IntegrityError as clash:
            self._session.rollback()
            if "uq_wave_order" in str(clash.orig):
                raise OrderTaken(
                    "Two waves in this batch, or one of them and a wave already stored, claim "
                    "the same /progression_config/order."
                ) from clash
            raise

        ids = [document.id for document in documents]
        rows = self._session.execute(
            text(f"select {SUMMARY_COLUMNS} from wave where project_id = :p and wave_id = any(:w)"),
            {"p": self._project, "w": ids},
        ).all()
        found = {row.wave_id: _summary(row) for row in rows}
        # In the order they were sent, so a caller can line the answer up with its input.
        return [found[wave_id] for wave_id in ids if wave_id in found]



def _summary(row: Any) -> WaveSummary:
    return WaveSummary(
        id=row.wave_id,
        name=row.name,
        order=row.wave_order,
        schema_version=row.schema_version,
        published=row.published,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _level_key(level_id: str) -> uuid.UUID | None:
    """A level id as the database holds it, or nothing for a string that cannot be one.

    A malformed id gets the answer an unknown one gets. Telling them apart says which ids are
    well formed, which nobody can act on; and passing it to the database fails the cast to
    uuid, which surfaced as a 500 on the activate route before this check existed.
    """
    try:
        return uuid.UUID(level_id)
    except ValueError:
        return None


def _constraint(clash: IntegrityError) -> str | None:
    """The constraint PostgreSQL refused with, read from the error's diagnostics rather than
    its message, so rewording or another server locale cannot change the answer."""
    diagnostics = getattr(clash.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None)
    return name if isinstance(name, str) else None


# The membership rules the schema keeps, and what each means to an author.
MEMBERSHIP_RULES = {
    "pk_wave_level_wave": "/waves: a level plays each wave once, and this list names one twice.",
    "uq_wave_level_wave_position": (
        "/waves: two waves cannot share a position in a level. Somebody else changed this "
        "level at the same moment; read it again and resend."
    ),
    "fk_wave_level_wave_wave": "/waves: a wave in this list is not in this project.",
}


def membership_rejection(clash: IntegrityError) -> Rejected | None:
    """A refusal by one of the membership rules, as a rejection an author can act on; nothing
    for any other violation, which is a fault rather than an author's mistake."""
    rule = MEMBERSHIP_RULES.get(_constraint(clash) or "")
    return None if rule is None else Rejected(rule)
