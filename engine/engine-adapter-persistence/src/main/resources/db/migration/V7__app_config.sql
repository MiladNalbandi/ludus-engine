-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Application configuration: the settings a game client reads at launch.
--
-- One row per project, and the primary key says so. Configuration is singular -- there is not a
-- list of configurations one of which is current -- and a table that allowed two would need a rule
-- somewhere choosing between them.
--
-- The same column pair as `wave`, for the same reason: the document is stored verbatim so that the
-- ETag over its bytes is stable, and the generated jsonb column exists only for indexing. See
-- V4__wave.sql for the full argument; it applies here unchanged, and this table is served to every
-- client on every launch, so a hash that churns costs more here than anywhere else.

create table app_config (
    project_id   uuid not null,
    config_json  text not null,
    updated_at   timestamp with time zone not null,

    constraint pk_app_config primary key (project_id),
    constraint fk_app_config_project foreign key (project_id) references project (id) on delete cascade
);
