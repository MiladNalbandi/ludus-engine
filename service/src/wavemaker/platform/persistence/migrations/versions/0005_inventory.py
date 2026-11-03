"""Items, the schema their attributes answer to, and what players hold.

Revision ID: 0005
Revises: 0004m

The inventory app's tables, carried over from the Java's V10 and V10.1 with three changes:

- Each table carries the app's name as a prefix, as `economy_balance` does, so an app's tables
  can be told from the platform's and from another app's at a glance.
- An inventory row's key includes the project. The Java keyed it on (player, item), which is
  the wallet's shape, and the wallet then needed a `where` on its upsert so a grant from one
  project could not add to a row of another's. With the project in the key, the two can never
  conflict, so there is nothing for that `where` to catch.
- The attributes are refused unless they are a JSON object, by the database as well as by the
  application, so a row written past the service is held to the same rule.

The tables are written here, in the platform's migration history, because that is the only
history this service runs today. A plugin carrying its own migrations is R5's to build.
"""

from alembic import op

revision = "0005"
down_revision = "0004m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The project's own JSON Schema for item attributes, stored as the text it was set as. One
    # row at most per project; no row validates nothing, which is the right default for a game
    # that has not yet decided what its items look like.
    #
    # Text only, with no jsonb beside it: the schema is never queried, only read back whole and
    # handed to a validator. The size limit is the application's, repeated here so a schema
    # written past the service cannot be one that every later save pays for.
    op.execute("""
        create table inventory_item_schema (
            project_id   uuid        not null,
            schema_json  text        not null,
            updated_at   timestamptz not null,

            constraint pk_inventory_item_schema primary key (project_id),
            constraint fk_inventory_item_schema_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint ck_inventory_item_schema_size check (octet_length(schema_json) <= 65536)
        )
    """)

    # The same pair as a wave's:
    #
    #   attributes_json text   what the editor sent, stored verbatim and served back verbatim
    #   attributes      jsonb  generated from it, for queries such as "every fire item"
    #
    # jsonb reorders keys and normalises numbers, so the text is the document and the jsonb is
    # only an index over it.
    op.execute("""
        create table inventory_item (
            project_id       uuid         not null,
            item_id          varchar(64)  not null,
            name             varchar(255) not null,
            -- The project's vocabulary: 'weapon', 'consumable', 'cosmetic'. Not an enum, for the
            -- same reason a currency is not one.
            item_type        varchar(64)  not null,
            -- An opaque reference the game resolves. Not a URL this service fetches.
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
    op.execute("create index ix_inventory_item_type on inventory_item (project_id, item_type)")
    op.execute("create index ix_inventory_item_attributes on inventory_item using gin (attributes)")

    # How many of each item each player holds. A row at zero is kept, because "had one and used
    # it" is worth telling apart from "never had one" when a game shows a collection.
    op.execute("""
        create table inventory_entry (
            project_id  uuid        not null,
            player_id   uuid        not null,
            item_id     varchar(64) not null,
            quantity    bigint      not null,
            updated_at  timestamptz not null,

            constraint pk_inventory_entry primary key (project_id, player_id, item_id),
            constraint fk_inventory_entry_project foreign key (project_id)
                references project (id) on delete cascade,
            -- Both halves composite with the project, so a row cannot pair a player from one
            -- project with an item from another: it fails to be insertable rather than failing
            -- a check somewhere. Removing a player or an item removes the rows, in the
            -- database, rather than in whichever code path remembered to.
            constraint fk_inventory_entry_player foreign key (player_id, project_id)
                references player (id, project_id) on delete cascade,
            constraint fk_inventory_entry_item foreign key (project_id, item_id)
                references inventory_item (project_id, item_id) on delete cascade,
            -- The guard a balance has: taking more than somebody holds fails here, whichever
            -- code path issued it.
            constraint ck_inventory_entry_not_negative check (quantity >= 0)
        )
    """)
    # "Who holds this item", which deleting an item asks through its foreign key.
    op.execute("create index ix_inventory_entry_item on inventory_entry (project_id, item_id)")


def downgrade() -> None:
    op.execute("drop table if exists inventory_entry")
    op.execute("drop table if exists inventory_item")
    op.execute("drop table if exists inventory_item_schema")
