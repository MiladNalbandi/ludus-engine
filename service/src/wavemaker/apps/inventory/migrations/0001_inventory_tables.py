"""Items, the schema their attributes answer to, and what players hold.

Revision ID: 0001
Revises: (none — the first revision of inventory's own history)

The first revision of inventory's own history, which the platform records in
`inventory_alembic_version`. It creates the same three tables, constraints and indexes as the
platform's `0005_inventory`, which created them before an app could carry its own migrations.

That revision cannot be edited and runs on every database, so here every statement is
`if not exists`: on a database that ran 0005 this revision changes nothing and the tables are
adopted as they are; on one that never did — a platform whose history no longer carries them —
it creates them. A test runs both and compares the two catalogs column by column and constraint
by constraint, so the two can never quietly come apart.

The design notes for each table are in 0005 and are not repeated here.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        create table if not exists inventory_item_schema (
            project_id   uuid        not null,
            schema_json  text        not null,
            updated_at   timestamptz not null,

            constraint pk_inventory_item_schema primary key (project_id),
            constraint fk_inventory_item_schema_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint ck_inventory_item_schema_size check (octet_length(schema_json) <= 65536)
        )
    """)

    op.execute("""
        create table if not exists inventory_item (
            project_id       uuid         not null,
            item_id          varchar(64)  not null,
            name             varchar(255) not null,
            item_type        varchar(64)  not null,
            sprite_ref       varchar(255),
            attributes_json  text         not null,
            attributes       jsonb generated always as (attributes_json::jsonb) stored,
            created_at       timestamptz  not null,
            updated_at       timestamptz  not null,

            constraint pk_inventory_item primary key (project_id, item_id),
            constraint fk_inventory_item_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint ck_inventory_item_id_format check (item_id ~ '^[a-z0-9_]+$'),
            constraint ck_inventory_item_type_format check (item_type ~ '^[a-z0-9_]+$'),
            constraint ck_inventory_item_name_not_blank check (length(trim(name)) > 0),
            constraint ck_inventory_item_attributes_object
                check (jsonb_typeof(attributes_json::jsonb) = 'object')
        )
    """)
    op.execute(
        "create index if not exists ix_inventory_item_type "
        "on inventory_item (project_id, item_type)"
    )
    op.execute(
        "create index if not exists ix_inventory_item_attributes "
        "on inventory_item using gin (attributes)"
    )

    op.execute("""
        create table if not exists inventory_entry (
            project_id  uuid        not null,
            player_id   uuid        not null,
            item_id     varchar(64) not null,
            quantity    bigint      not null,
            updated_at  timestamptz not null,

            constraint pk_inventory_entry primary key (project_id, player_id, item_id),
            constraint fk_inventory_entry_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint fk_inventory_entry_player foreign key (player_id, project_id)
                references player (id, project_id) on delete cascade,
            constraint fk_inventory_entry_item foreign key (project_id, item_id)
                references inventory_item (project_id, item_id) on delete cascade,
            constraint ck_inventory_entry_not_negative check (quantity >= 0)
        )
    """)
    op.execute(
        "create index if not exists ix_inventory_entry_item "
        "on inventory_entry (project_id, item_id)"
    )


def downgrade() -> None:
    op.execute("drop table if exists inventory_entry")
    op.execute("drop table if exists inventory_item")
    op.execute("drop table if exists inventory_item_schema")
