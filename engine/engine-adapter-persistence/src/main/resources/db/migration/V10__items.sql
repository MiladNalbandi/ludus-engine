-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Items, and what players have of them.
--
-- The models this is reshaped from had an item type that assumed particular effects -- an enum of
-- one game's power-ups, with the engine knowing what each did. A second game then needed a fork.
--
-- Here an item is: an identifier, a display name, an optional sprite reference, a type drawn from
-- the project's own vocabulary, and a free-form attributes document. The engine interprets none of
-- it. What stops the attributes being a junk drawer is that they are validated against a schema
-- the project owns -- so a project that wants `{"damage": 12}` to mean something declares that, and
-- Ludus ships knowing nothing about damage.

create table item_schema (
    project_id  uuid not null,

    -- The project's own JSON Schema for item attributes, stored verbatim like every other document
    -- here. A project with no row validates nothing, which is the right default: a game that has
    -- not decided what its items look like should not be stopped from creating one.
    schema_json text not null,
    updated_at  timestamp with time zone not null,

    constraint pk_item_schema primary key (project_id),
    constraint fk_item_schema_project foreign key (project_id) references project (id) on delete cascade
);

create table item (
    project_id      uuid         not null,
    item_id         varchar(64)  not null,

    name            varchar(255) not null,

    -- The project's vocabulary: 'weapon', 'consumable', 'cosmetic'. Not an enum, for the same
    -- reason the currency code is not one.
    item_type       varchar(64)  not null,

    -- An opaque reference to an image, resolved by the game. Not a path and not a URL the engine
    -- fetches: an engine that dereferenced this would be a request-forgery hole with extra steps.
    sprite_ref      varchar(255),

    attributes_json text         not null,
    created_at      timestamp with time zone not null,
    updated_at      timestamp with time zone not null,

    constraint pk_item primary key (project_id, item_id),
    constraint fk_item_project foreign key (project_id) references project (id) on delete cascade,
    constraint ck_item_id_format check (regexp_like(item_id, '^[a-z0-9_]+$')),
    constraint ck_item_type_format check (regexp_like(item_type, '^[a-z0-9_]+$')),

    -- For the composite foreign key an inventory row needs, so a player cannot hold an item from
    -- another project.
    constraint uq_item_id_project unique (item_id, project_id)
);

create index ix_item_type on item (project_id, item_type, item_id);

create table player_inventory (
    project_id uuid        not null,
    player_id  uuid        not null,
    item_id    varchar(64) not null,
    quantity   bigint      not null,
    updated_at timestamp with time zone not null,

    constraint pk_player_inventory primary key (player_id, item_id),

    constraint fk_player_inventory_player foreign key (player_id, project_id)
        references player (id, project_id) on delete cascade,

    -- Both halves composite, so an inventory row cannot pair a player from one project with an
    -- item from another. Deleting an item removes it from every inventory, in the database.
    constraint fk_player_inventory_item foreign key (item_id, project_id)
        references item (item_id, project_id) on delete cascade,

    -- The same guard as a balance: taking more than somebody has fails here whatever code path
    -- issued it. A row at zero is allowed, because "had one and used it" is worth telling apart
    -- from "never had one" when a game shows a collection.
    constraint ck_player_inventory_not_negative check (quantity >= 0)
);
