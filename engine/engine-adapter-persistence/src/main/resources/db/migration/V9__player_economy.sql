-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- What a player has, and how far they have got.
--
-- Two tables and one deliberate absence. There is no `stage` column: a player's stage is derived
-- from their XP and the project's own curve, and storing it would be a second truth for the same
-- fact -- one that goes stale the moment somebody edits the curve, silently, for every player at
-- once.

create table player_currency (
    project_id  uuid        not null,
    player_id   uuid        not null,

    -- The project's own vocabulary: coins, gems, energy. Not an enum, because an enum here means a
    -- release of Ludus every time a game invents a currency.
    currency    varchar(40) not null,

    amount      bigint      not null,
    updated_at  timestamp with time zone not null,

    constraint pk_player_currency primary key (player_id, currency),

    -- Composite, so a balance cannot belong to a different project from its player.
    constraint fk_player_currency_player foreign key (player_id, project_id)
        references player (id, project_id) on delete cascade,

    -- The overdraft guard, in the database rather than in a service method. A debit that would go
    -- below zero fails here whatever code path issued it, including one written later that forgot
    -- to check -- which is the only version of this rule worth having.
    constraint ck_player_currency_not_negative check (amount >= 0),
    constraint ck_player_currency_code check (regexp_like(currency, '^[a-z0-9_]+$'))
);

-- The curve, as data the project owns.
--
-- The models this is reshaped from had an XP curve with fixed semantics baked into code. A game
-- whose difficulty ramp differs then needs a fork. Rows instead: a project defines its own stages,
-- and Ludus ships knowing nothing about how steep they are.
create table xp_stage (
    project_id  uuid    not null,
    stage       integer not null,

    -- The total XP at which this stage begins. Cumulative, not per-stage, because "how far to the
    -- next one" is then subtraction rather than a running sum over every earlier row.
    xp_required bigint  not null,
    label       varchar(120),

    constraint pk_xp_stage primary key (project_id, stage),
    constraint fk_xp_stage_project foreign key (project_id) references project (id) on delete cascade,
    constraint ck_xp_stage_not_negative check (stage >= 0 and xp_required >= 0),

    -- Two stages cannot begin at the same total, which would make "which stage is this" ambiguous.
    constraint uq_xp_stage_threshold unique (project_id, xp_required)
);

create table player_progress (
    project_id  uuid   not null,
    player_id   uuid   not null,
    xp          bigint not null,
    updated_at  timestamp with time zone not null,

    constraint pk_player_progress primary key (player_id),
    constraint fk_player_progress_player foreign key (player_id, project_id)
        references player (id, project_id) on delete cascade,
    constraint ck_player_progress_xp_not_negative check (xp >= 0)
);
