"""AC-7: an app's own migrations, run against PostgreSQL and judged by what they did.

Each refusal is a migration that does one thing it may not, next to one table it may create.
The test checks the refusal names the object, and that the allowed table is gone too: the
whole history is rolled back, not just the statement that was refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.community.postgres import PostgresContainer

import wavemaker.apps.inventory
from tests.integration.plugin_kit import revision, write_app
from wavemaker.platform.kernel.errors import PermissionRefused
from wavemaker.platform.kernel.manifest import AppManifest
from wavemaker.platform.persistence.engine import MIGRATIONS as PLATFORM_MIGRATIONS
from wavemaker.platform.plugins import outbound
from wavemaker.platform.plugins.loader import read_manifest
from wavemaker.platform.plugins.migrations import AppMigrationError, migrate_app
from wavemaker.platform.tenancy import ensure_project

INVENTORY = Path(wavemaker.apps.inventory.__file__).resolve().parent
OWN = "create table achievements_badge (id text primary key)"


def app_with(
    tmp_path: Path, *revisions: str, name: str = "achievements"
) -> tuple[AppManifest, Path]:
    migrations = {
        f"{number:04d}_step.py": revision(
            body,
            revision_id=f"{number:04d}",
            down=None if number == 1 else f"{number - 1:04d}",
        )
        for number, body in enumerate(revisions, start=1)
    }
    folder = write_app(tmp_path / uuid.uuid4().hex, name, migrations=migrations)
    return read_manifest(folder / "manifest.toml"), folder / "migrations"


def tables(url: str) -> set[str]:
    engine = create_engine(url)
    with engine.connect() as connection:
        found = set(
            connection.execute(
                text("select tablename from pg_tables where schemaname = 'public'")
            ).scalars()
        )
    engine.dispose()
    return found


def scalar(url: str, query: str) -> object:
    engine = create_engine(url)
    with engine.connect() as connection:
        value = connection.execute(text(query)).scalar()
    engine.dispose()
    return value


def test_ac7_an_apps_own_tables_are_created_recorded_and_versioned(
    tmp_path: Path, database_url: str
) -> None:
    manifest, migrations = app_with(tmp_path, OWN)

    migrate_app(database_url, manifest, migrations)

    assert {"achievements_badge", "achievements_alembic_version"} <= tables(database_url)
    assert scalar(database_url, "select version_num from achievements_alembic_version") == "0001"
    assert scalar(database_url, "select count(*) from alembic_version") == 1, (
        "the platform's own history is untouched: one head, its own"
    )
    owned = scalar(
        database_url,
        "select string_agg(object, ',' order by object) from wavemaker_app_object "
        "where app = 'achievements'",
    )
    assert (
        owned == "relation public.achievements_alembic_version,relation public.achievements_badge"
    )


def test_ac7_running_a_history_again_changes_nothing(tmp_path: Path, database_url: str) -> None:
    manifest, migrations = app_with(tmp_path, OWN)
    migrate_app(database_url, manifest, migrations)
    migrate_app(database_url, manifest, migrations)
    assert scalar(database_url, "select version_num from achievements_alembic_version") == "0001"


def test_ac7_a_later_version_may_change_the_tables_it_owns(
    tmp_path: Path, database_url: str
) -> None:
    first, migrations = app_with(tmp_path, OWN)
    migrate_app(database_url, first, migrations)

    second, migrations = app_with(
        tmp_path,
        OWN,
        "alter table achievements_badge add column title text",
    )
    migrate_app(database_url, second, migrations)

    assert scalar(database_url, "select version_num from achievements_alembic_version") == "0002"
    assert (
        scalar(
            database_url,
            "select count(*) from information_schema.columns "
            "where table_name = 'achievements_badge' and column_name = 'title'",
        )
        == 1
    )


@pytest.mark.parametrize(
    ("statements", "named"),
    [
        (
            "create table player_backdoor (id text primary key)",
            "creates table public.player_backdoor",
        ),
        ("create table leaderboard_scores (id text)", "creates table public.leaderboard_scores"),
        ("create index achievements_ix on player (external_id)", "on public.player"),
        ("alter table project add column achievements_note text", "alters table public.project"),
        ("update project set name = 'renamed by a plugin'", "writes rows of table public.project"),
        ("delete from project", "writes rows of table public.project"),
        (
            "insert into project (id, slug, name, created_at) "
            "values (gen_random_uuid(), 'other', 'Other', now())",
            "writes rows of table public.project",
        ),
        ("truncate refresh_token cascade", "alters table public.refresh_token"),
        ("drop table api_key cascade", "drops table public.api_key"),
        ("comment on table player is 'mine now'", "alters table public.player"),
        ("grant all on account to public", "alters table public.account"),
        ("create view leaked as select * from account", "creates view public.leaked"),
        ("create sequence counter", "creates sequence public.counter"),
        ("create type mood as enum ('happy')", "creates type public.mood"),
        (
            "create function steal() returns int language sql as 'select 1'",
            "creates function public.steal()",
        ),
        ("create schema exfiltration", "creates schema exfiltration"),
        ("create role achievements_intruder", "creates role achievements_intruder"),
        ("create extension if not exists pgcrypto", "creates extension pgcrypto"),
        (
            "create function achievements_t() returns trigger language plpgsql "
            "as 'begin return new; end'\n"
            "create trigger achievements_watch before insert on player "
            "for each row execute function achievements_t()",
            "alters table public.player",
        ),
    ],
)
def test_ac7_a_migration_touching_what_is_not_its_own_is_refused_and_rolled_back(
    tmp_path: Path,
    database_url: str,
    session_factory: sessionmaker[Session],
    statements: str,
    named: str,
) -> None:
    with session_factory() as session:
        ensure_project(session, "default", "Default")
    manifest, migrations = app_with(tmp_path, f"{OWN}\n{statements}")
    before = tables(database_url)

    with pytest.raises(PermissionRefused) as refused:
        migrate_app(database_url, manifest, migrations)

    assert named in str(refused.value)
    assert "rolled back" in str(refused.value)
    assert tables(database_url) == before, "everything the history did is undone"
    assert scalar(database_url, "select string_agg(name, ',') from project") == "Default"
    assert (
        scalar(database_url, "select count(*) from pg_roles where rolname like 'achievements%'")
        == 0
    )


def test_ac7_a_name_carrying_the_prefix_does_not_make_a_platform_table_the_apps(
    tmp_path: Path, database_url: str
) -> None:
    """A plugin called `api` owns `api_*` — but not the platform's `api_key`, which was there
    before its history ever ran."""
    manifest, migrations = app_with(
        tmp_path,
        "create table api_extra (id text)\nalter table api_key add column api_backdoor text",
        name="api",
    )
    with pytest.raises(PermissionRefused) as refused:
        migrate_app(database_url, manifest, migrations)
    assert "alters table public.api_key" in str(refused.value)
    assert "api_extra" not in tables(database_url)


def test_ac7_an_app_cannot_write_the_record_of_what_it_owns(
    tmp_path: Path, database_url: str
) -> None:
    first, migrations = app_with(tmp_path, OWN)
    migrate_app(database_url, first, migrations)

    grab, migrations = app_with(
        tmp_path,
        OWN,
        "insert into wavemaker_app_object (object, app) values ('relation public.player', "
        "'achievements')",
    )
    with pytest.raises(PermissionRefused) as refused:
        migrate_app(database_url, grab, migrations)
    assert "writes rows of table public.wavemaker_app_object" in str(refused.value)


def test_ac7_a_migration_that_commits_is_refused_and_says_what_it_could_not_undo(
    tmp_path: Path, database_url: str
) -> None:
    """The limit, stated by a test: what ran before the COMMIT is permanent. The runner
    notices the transaction changed and refuses loudly; it cannot take that part back."""
    manifest, migrations = app_with(
        tmp_path, "create table player_smuggled (id text)\ncommit\n" + OWN
    )
    with pytest.raises(PermissionRefused) as refused:
        migrate_app(database_url, manifest, migrations)
    assert "ended the transaction" in str(refused.value)
    assert "achievements_badge" not in tables(database_url), "after the COMMIT is rolled back"
    assert "player_smuggled" in tables(database_url), "before it is not, and the test says so"


def test_ac8_a_migration_may_not_reach_the_network(tmp_path: Path, database_url: str) -> None:
    folder = write_app(
        tmp_path / "src",
        "achievements",
        migrations={
            "0001_step.py": (
                "import socket\n\nrevision = '0001'\ndown_revision = None\n"
                "branch_labels = None\ndepends_on = None\n\n\n"
                "def upgrade() -> None:\n"
                "    socket.getaddrinfo('localhost', 80)\n"
            )
        },
    )
    with pytest.raises(AppMigrationError) as refused:
        migrate_app(database_url, read_manifest(folder / "manifest.toml"), folder / "migrations")
    assert isinstance(refused.value.__cause__, outbound.OutboundRefused)


@pytest.fixture
def database_before_inventory(postgres: PostgresContainer) -> Iterator[str]:
    """A database whose platform history stops at 0004m: one that never ran 0005_inventory."""
    shared = postgres.get_connection_url()
    name = f"before_inventory_{uuid.uuid4().hex}"
    server = create_engine(shared, isolation_level="AUTOCOMMIT")
    with server.connect() as connection:
        connection.execute(text(f'create database "{name}"'))
    url = make_url(shared).set(database=name).render_as_string(hide_password=False)
    config = Config()
    config.set_main_option("script_location", str(PLATFORM_MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0004m")
    try:
        yield url
    finally:
        with server.connect() as connection:
            connection.execute(text(f'drop database if exists "{name}" with (force)'))
        server.dispose()


STRUCTURE = text(
    """
    select c.relname || ' ' || c.relkind::text || ' ' || coalesce((
             select string_agg(a.attname || ':' || format_type(a.atttypid, a.atttypmod) || ':'
                               || a.attnotnull || ':' || a.attgenerated::text || ':'
                               || coalesce(pg_get_expr(d.adbin, d.adrelid), ''),
                               ',' order by a.attnum)
             from pg_attribute a
             left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
             where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped), '')
           || ' ' || coalesce((
             select string_agg(con.conname || '=' || pg_get_constraintdef(con.oid), ','
                               order by con.conname)
             from pg_constraint con where con.conrelid = c.oid), '')
           || ' ' || coalesce(pg_get_indexdef(c.oid), '')
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relname like any (array['inventory\\_%', '%\\_inventory\\_%'])
      and c.relname <> 'inventory_alembic_version' and c.relname not like 'inventory_alembic%'
    order by c.relname
    """
)


def structure(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(STRUCTURE).scalars())


def test_ac7_inventorys_own_history_builds_exactly_what_0005_built(
    database_url: str, database_before_inventory: str
) -> None:
    """0005 cannot be edited and runs everywhere, so inventory's history adopts its tables. This
    is what makes adopting safe: on a database that never ran 0005, the history builds the same
    tables, column by column, constraint by constraint, index by index."""
    manifest = read_manifest(INVENTORY / "manifest.toml")
    assert "inventory_item" not in tables(database_before_inventory)

    migrate_app(database_before_inventory, manifest, INVENTORY / "migrations")

    built_by_0005 = create_engine(database_url)
    built_by_plugin = create_engine(database_before_inventory)
    try:
        expected = structure(built_by_0005)
        assert len(expected) == 9, expected  # three tables, three keys, three indexes
        assert structure(built_by_plugin) == expected
    finally:
        built_by_0005.dispose()
        built_by_plugin.dispose()


def test_ac7_inventorys_history_adopts_the_tables_0005_made_and_owns_them(
    database_url: str,
) -> None:
    manifest = read_manifest(INVENTORY / "manifest.toml")
    migrate_app(database_url, manifest, INVENTORY / "migrations")

    owned = scalar(
        database_url,
        "select string_agg(object, ',' order by object) from wavemaker_app_object "
        "where app = 'inventory'",
    )
    assert owned == (
        "relation public.inventory_alembic_version,relation public.inventory_entry,"
        "relation public.inventory_item,relation public.inventory_item_schema"
    )
    assert scalar(database_url, "select version_num from inventory_alembic_version") == "0001"
