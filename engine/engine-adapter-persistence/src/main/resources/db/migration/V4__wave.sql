-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Waves: the first content type, and the shape every later one copies.
--
-- The column pair below is the decision the rest of the content design hangs off.
--
--   config_json text   the bytes the client sent, stored verbatim
--   config      jsonb  generated from them, for indexing only (postgresql/V4.1)
--
-- The public ETag for a raw document is sha256 of the stored bytes, so those bytes have to be
-- stable. Storing as jsonb would not be: PostgreSQL normalises whitespace and reorders keys.
-- Deserialising and re-serialising on the write path would not be either -- null handling differs,
-- and 1.0 comes back as 1.
--
-- Neither would break anything visibly. Both would move the ETag on every save even when the
-- author changed nothing, so every installed client re-downloads the whole catalogue on next
-- launch. On mobile that is a bandwidth bill and one-star reviews, arriving weeks later with
-- nothing obvious to connect them to.
--
-- So: the bytes are the source, the jsonb column is derived from them, and every indexed column
-- below is filled by READING the document rather than by re-serialising it.

create table wave (
    project_id      uuid         not null,
    wave_id         varchar(64)  not null,

    -- Present from the first content migration, deliberately, though nothing reads them yet.
    -- When entity, behaviour and content types become data (#12), that work is a decomposition
    -- rather than a rewrite only if the discriminators were already here to decompose along.
    content_type    varchar(64)  not null default 'wave',
    schema_uri      varchar(512) not null,
    schema_version  integer      not null,

    -- Read out of the document, never accepted as request fields.
    name            varchar(255) not null,
    wave_order      integer      not null,

    -- Authoritative. The document mirrors it so a document read in isolation still says whether
    -- it was live, but this column is what the serving routes actually consult.
    published       boolean      not null default false,

    -- The bytes, verbatim. A generated jsonb column is derived from this for indexing, and
    -- because that is PostgreSQL-specific it lives in postgresql/V4.1 rather than here.
    config_json     text         not null,

    created_at      timestamp with time zone not null,
    updated_at      timestamp with time zone not null,

    constraint pk_wave primary key (project_id, wave_id),
    constraint fk_wave_project foreign key (project_id) references project (id) on delete cascade,
    -- The same pattern as io.ludus.domain.shared.Slug and as the schema's own `id`.
    constraint ck_wave_id_format check (regexp_like(wave_id, '^[a-z0-9_]+$')),
    constraint ck_wave_order_not_negative check (wave_order >= 0),
    constraint ck_wave_schema_version_positive check (schema_version >= 1)
);

-- An order collision is a constraint violation rather than racy application logic. The use case
-- checks first so the author gets a useful 422 pointing at /progression_config/order; this exists
-- so that two concurrent writes cannot both succeed in claiming order 3.
create unique index uq_wave_order on wave (project_id, wave_order);

-- The serving routes filter on published within a project, and that is the only list query.
create index ix_wave_published on wave (project_id, published);
