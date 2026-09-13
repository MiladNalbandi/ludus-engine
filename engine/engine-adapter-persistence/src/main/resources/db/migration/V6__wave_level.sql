-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Wave levels: an ordered sequence of waves, and which one a game client is currently playing.
--
-- Three things here are structural that were application logic in the codebase this was extracted
-- from, and each of them was a bug there at least once.

create table wave_level (
    id          uuid         not null,
    project_id  uuid         not null,
    name        varchar(255) not null,
    description text,
    created_at  timestamp with time zone not null,
    updated_at  timestamp with time zone not null,

    constraint pk_wave_level primary key (id),
    constraint fk_wave_level_project foreign key (project_id) references project (id) on delete cascade,

    -- Redundant against the primary key, and required. It is the key the membership table's
    -- composite foreign key points at, which is what makes a level and its waves provably belong
    -- to the same project rather than merely usually belonging to it.
    constraint uq_wave_level_id_project unique (id, project_id)
);

create index ix_wave_level_project on wave_level (project_id, name);

-- Which waves are in a level, and in what order.
create table wave_level_wave (
    project_id     uuid        not null,
    wave_level_id  uuid        not null,
    wave_id        varchar(64) not null,
    position       integer     not null,

    constraint pk_wave_level_wave primary key (wave_level_id, wave_id),

    -- The composite foreign key this table never had. Keyed on (id, project_id) rather than on id
    -- alone, so the project_id column here cannot disagree with the level's: a row claiming a
    -- level from project A and a wave from project B does not fail a check somewhere, it fails to
    -- be insertable.
    constraint fk_wave_level_wave_level foreign key (wave_level_id, project_id)
        references wave_level (id, project_id) on delete cascade,

    -- And the other half: a wave is identified by (project_id, wave_id), so the reference to one
    -- must carry both. Deleting a wave removes it from every level that used it, in the database,
    -- rather than in whichever service method happened to remember.
    constraint fk_wave_level_wave_wave foreign key (project_id, wave_id)
        references wave (project_id, wave_id) on delete cascade,

    -- Two waves cannot share a slot. The use case checks first for a useful 422; this exists so
    -- that two concurrent writes cannot both succeed.
    constraint uq_wave_level_wave_position unique (wave_level_id, position),
    constraint ck_wave_level_wave_position_not_negative check (position >= 0)
);

-- Which level is active, as a table rather than a boolean column.
--
-- The obvious design is `active boolean` on wave_level plus a partial unique index --
-- `create unique index ... on wave_level (project_id) where active` -- and that is what the
-- roadmap issue proposed. It is PostgreSQL-only: H2 does not support a WHERE clause on an index,
-- so it would have had to live in db/vendor/postgresql alongside the generated jsonb column.
--
-- That is fine for a column nothing reads. It is not fine for a constraint. The slice tests run
-- the shipped migrations against H2, and a rule that is absent there is a rule those tests cannot
-- prove -- so the one invariant this feature exists to guarantee would be unenforced in exactly
-- the environment where it is checked.
--
-- A primary key on project_id says the same thing in SQL every database has, and says it more
-- precisely: at most one active level per project, which is the truth (a project with no levels
-- has no active one). Deleting the active level cascades this row away, leaving the project with
-- nothing active rather than a pointer to something that is gone.
create table wave_level_activation (
    project_id     uuid not null,
    wave_level_id  uuid not null,
    activated_at   timestamp with time zone not null,

    constraint pk_wave_level_activation primary key (project_id),
    constraint fk_wave_level_activation_project foreign key (project_id)
        references project (id) on delete cascade,
    constraint fk_wave_level_activation_level foreign key (wave_level_id, project_id)
        references wave_level (id, project_id) on delete cascade
);
