-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Players: who is playing, per project.
--
-- The engine does not know what a player *is*. It stores an identifier the game already has -- a
-- device id, an account id from a platform SDK, whatever the game uses -- and treats it as opaque.
-- Anything else would mean the engine owning player accounts, with the password resets, the email
-- verification and the deletion requests that come with them, for no benefit: the game already has
-- an identity system or has deliberately chosen not to.
--
-- That identifier is `external_id`, and it is unique within a project and meaningless across
-- projects. The engine's own `id` is what everything else refers to, so a game that changes its
-- identity scheme migrates one column rather than every row that mentions a player.

create table player (
    id           uuid         not null,
    project_id   uuid         not null,

    -- The game's own identifier. Opaque, and never parsed or interpreted here.
    external_id  varchar(190) not null,

    -- Optional, and set by the player. Not unique: two people may both be "Alex", and enforcing
    -- otherwise means telling somebody their name is taken, which is a feature this does not have.
    display_name varchar(120),

    created_at   timestamp with time zone not null,
    -- Updated on every session. It is what makes "how many players last week" answerable without
    -- an events table, and it is the only field the engine writes on its own.
    last_seen_at timestamp with time zone not null,

    constraint pk_player primary key (id),
    constraint fk_player_project foreign key (project_id) references project (id) on delete cascade,

    -- One row per identifier per project. Without this, a client retrying a session start during a
    -- network blip creates a second player and the first one's progress becomes unreachable.
    constraint uq_player_external_id unique (project_id, external_id),

    -- Required for the composite foreign keys the later live-ops tables use, so that a player's
    -- currency, inventory and scores cannot belong to a different project from the player.
    constraint uq_player_id_project unique (id, project_id),

    constraint ck_player_external_id_not_blank check (length(trim(external_id)) > 0)
);

-- "Who has been active recently", which is the one query this table exists to answer beyond lookup.
create index ix_player_last_seen on player (project_id, last_seen_at desc);
