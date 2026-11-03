"""An app's own migrations: run in one transaction, judged by what they did, and kept only if
every change was the app's to make.

**One history per app, each with its own version table.** An app ships `migrations/`, a
directory of ordinary Alembic revision files, and its history is recorded in
`<prefix>alembic_version` — `inventory_alembic_version` — rather than in the platform's
`alembic_version`. That table carries the app's prefix, so it is the app's like any other.

A branch per app inside the platform's history was the other choice, and it is worse in the
way that matters most: every branch's head is a row in the one `alembic_version` table, so a
plugin that is removed leaves a row naming a revision whose file no longer exists, and Alembic
then refuses to migrate *anything* — one uninstalled plugin stops the platform starting. A
separate table per app means an app's history can come and go without the platform's noticing,
revision ids only have to be unique within one app, and nothing is ever added to the
platform's own `versions/`, whose heads other work extends in parallel.

**The transaction is the enforcement.** PostgreSQL runs DDL inside a transaction, so the
runner opens one, snapshots the catalog, runs the app's history, snapshots again, and commits
only when every difference is the app's own (see `persistence.catalog.judge`). Otherwise it
rolls back, and the refusal names each table. The platform's own history always runs first, so
an app may reference `project` and `player` with a foreign key; it may not change them.

**What an app owns is recorded,** in `wavemaker_app_object`, which the runner keeps and no app
may write. A name carrying the prefix is not enough on its own: the first time a plugin called
`api` runs, the platform's `api_key` already exists, and is not the plugin's.

**Tables the platform's history created on an app's behalf** before apps carried their own are
handed over by name, the first time that app's history runs. Today that is inventory's three,
created by `0005_inventory`: that revision cannot be edited, so on every database the
platform creates them, and inventory's own history adopts them with `create table if not
exists` (and is proved, by a test, to create exactly the same tables on a database that never
ran 0005).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text

from wavemaker.platform.kernel.errors import PermissionRefused, PlatformError
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.persistence.catalog import judge, relation_object, snapshot
from wavemaker.platform.persistence.engine import create_database_engine
from wavemaker.platform.plugins import outbound

ENVIRONMENT = Path(__file__).resolve().parent / "history"
MIGRATIONS = "migrations"
LEDGER = "wavemaker_app_object"

# Two replicas starting together must not run one app's history twice at once.
LOCK = 0x5741_5645  # "WAVE"

HANDED_OVER: dict[str, tuple[str, ...]] = {
    "inventory": ("inventory_item_schema", "inventory_item", "inventory_entry"),
}


class AppMigrationError(PlatformError):
    """An app's own migration failed to run."""


def version_table(manifest: AppManifest) -> str:
    return f"{manifest.table_prefix}alembic_version"


def migrate_app(url: str, manifest: AppManifest, migrations: Path) -> None:
    """Bring this app's own tables to the head of its history, or change nothing at all."""
    engine = create_database_engine(url)
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(text("select pg_advisory_xact_lock(:key)"), {"key": LOCK})
            _ensure_ledger(connection)
            _hand_over(connection, manifest)
            owned = _owned(connection, manifest)

            transaction = _transaction_id(connection)
            before = snapshot(connection)
            try:
                with outbound.acting_as(manifest):
                    _upgrade(connection, manifest, migrations)
            except Exception as failed:
                raise AppMigrationError(
                    f"The migrations of '{manifest.name}' ({migrations}) failed: {failed}"
                ) from failed

            if _transaction_id(connection) != transaction:
                # Whatever ran before the COMMIT is permanent and cannot be judged after the
                # fact. Refusing is all that is left, and it is loud.
                raise PermissionRefused(
                    f"The migrations of '{manifest.name}' ended the transaction they were run "
                    "in, so what they changed before that cannot be checked or rolled back. An "
                    "app's migration may not commit."
                )

            judgement = judge(before, snapshot(connection), manifest.table_prefix, owned)
            if judgement.refused:
                raise PermissionRefused(
                    f"The migrations of '{manifest.name}' were refused and rolled back: "
                    f"{'; '.join(judgement.refused)}. An app owns only the tables, types and "
                    f"functions it creates with its prefix, '{manifest.table_prefix}'."
                )
            _record(connection, manifest, judgement.created, judgement.dropped)
    finally:
        engine.dispose()


def migrations_of(directory: Path) -> Path | None:
    """An app's own history, if it carries one."""
    candidate = directory / MIGRATIONS
    return candidate if candidate.is_dir() else None


def _upgrade(connection: Connection, manifest: AppManifest, migrations: Path) -> None:
    config = Config()
    config.set_main_option("script_location", _option(ENVIRONMENT))
    config.set_main_option("version_locations", _option(migrations))
    config.set_main_option("path_separator", "os")
    config.attributes["connection"] = connection
    config.attributes["version_table"] = version_table(manifest)
    command.upgrade(config, "heads")


def _option(path: Path) -> str:
    # Alembic's options are interpolated, so a '%' in a path would be read as a variable.
    return str(path).replace("%", "%%")


def _transaction_id(connection: Connection) -> int:
    return int(connection.execute(text("select txid_current()")).scalar_one())


def _ensure_ledger(connection: Connection) -> None:
    connection.execute(
        text(
            f"""
            create table if not exists {LEDGER} (
                object  text not null,
                app     text not null,
                constraint pk_{LEDGER} primary key (object)
            )
            """
        )
    )


def _owned(connection: Connection, manifest: AppManifest) -> set[str]:
    rows = connection.execute(
        text(f"select object from {LEDGER} where app = :app"), {"app": manifest.name}
    )
    return {row.object for row in rows}


def _hand_over(connection: Connection, manifest: AppManifest) -> None:
    tables = HANDED_OVER.get(manifest.name, ())
    if not tables:
        return
    existing = connection.execute(
        text(
            """
            select n.nspname || '.' || c.relname as key
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = current_schema() and c.relname = any(:names)
              and c.relkind in ('r', 'p')
            """
        ),
        {"names": list(tables)},
    )
    _claim(connection, manifest, (relation_object(row.key) for row in existing))


def _record(
    connection: Connection, manifest: AppManifest, created: Iterable[str], dropped: Iterable[str]
) -> None:
    _claim(connection, manifest, created)
    for gone in dropped:
        connection.execute(
            text(f"delete from {LEDGER} where object = :object and app = :app"),
            {"object": gone, "app": manifest.name},
        )


def _claim(connection: Connection, manifest: AppManifest, objects: Iterable[str]) -> None:
    for item in objects:
        connection.execute(
            text(
                f"insert into {LEDGER} (object, app) values (:object, :app) "
                "on conflict (object) do nothing"
            ),
            {"object": item, "app": manifest.name},
        )
