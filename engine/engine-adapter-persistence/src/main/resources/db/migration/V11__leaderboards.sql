-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Leaderboards: one score per player per board.
--
-- A board is defined by the project, like a currency or an item type. The engine does not know what
-- "time_trial" means; it sorts numbers and says which way.

create table leaderboard (
    project_id uuid         not null,
    board_id   varchar(64)  not null,
    name       varchar(255) not null,

    -- Whether a bigger number is better. A lap time and a high score are both leaderboards and they
    -- sort opposite ways, so this is a property of the board rather than something a caller passes
    -- on every query -- where two callers would eventually disagree.
    descending boolean      not null default true,

    created_at timestamp with time zone not null,
    updated_at timestamp with time zone not null,

    constraint pk_leaderboard primary key (project_id, board_id),
    constraint fk_leaderboard_project foreign key (project_id) references project (id) on delete cascade,
    constraint ck_leaderboard_id_format check (regexp_like(board_id, '^[a-z0-9_]+$')),
    constraint uq_leaderboard_id_project unique (board_id, project_id)
);

create table leaderboard_entry (
    project_id uuid        not null,
    board_id   varchar(64) not null,
    player_id  uuid        not null,
    score      bigint      not null,
    updated_at timestamp with time zone not null,

    -- One score per player per board. A board that allowed several would need a rule for which one
    -- ranks, and every caller would have to know it.
    constraint pk_leaderboard_entry primary key (board_id, player_id),

    constraint fk_leaderboard_entry_board foreign key (board_id, project_id)
        references leaderboard (board_id, project_id) on delete cascade,
    constraint fk_leaderboard_entry_player foreign key (player_id, project_id)
        references player (id, project_id) on delete cascade
);

-- The index the ranking query runs on, in both directions.
--
-- player_id is part of it, and that is the whole reason paging works: scores tie constantly --
-- everybody who finished the tutorial has the same one -- so ordering by score alone is not a total
-- order, and a keyset cursor over a non-total order skips and repeats rows. The tie-break makes the
-- order total, and therefore the cursor exact.
create index ix_leaderboard_entry_desc on leaderboard_entry (project_id, board_id, score desc, player_id desc);
create index ix_leaderboard_entry_asc on leaderboard_entry (project_id, board_id, score asc, player_id asc);
