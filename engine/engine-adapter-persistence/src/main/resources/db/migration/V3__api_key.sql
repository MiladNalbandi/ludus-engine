-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- API keys, for game clients.
--
-- Only a digest is stored. The prefix is the first few characters of the key and is not secret:
-- it exists so a person can tell two keys apart in a list without being shown either of them.
-- It is deliberately not what a presented key is looked up by -- that is the digest, which is
-- unique, so a lookup is one indexed equality match with no collisions to resolve.

create table api_key (
    id             uuid         not null,
    project_id     uuid         not null,
    name           varchar(120) not null,
    prefix         varchar(16)  not null,
    secret_digest  varchar(64)  not null,
    role           varchar(16)  not null,
    created_at     timestamp with time zone not null,
    revoked_at     timestamp with time zone,

    constraint pk_api_key primary key (id),
    constraint fk_api_key_project foreign key (project_id) references project (id),
    constraint uq_api_key_digest unique (secret_digest),
    -- A key that can write is a key that can be leaked into a game binary and then used to write.
    -- Widening this is a migration and a deliberate decision, not a field someone can set.
    constraint ck_api_key_role check (role in ('VIEWER'))
);

create index ix_api_key_project on api_key (project_id);
