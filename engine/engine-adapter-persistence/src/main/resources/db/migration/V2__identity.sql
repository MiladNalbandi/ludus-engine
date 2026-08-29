-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Users, and the first tables to carry the project boundary V1 exists for.
--
-- Every table here has project_id NOT NULL with a foreign key to project. The unique constraint
-- on an address is (project_id, email) rather than (email): two projects may each have a user
-- with the same address, and they are different people as far as this engine is concerned.
--
-- Addresses are stored already lower-cased by the application. The constraint below refuses
-- anything else rather than folding case itself, so that a value written by something other than
-- the application cannot create a second account for the same mailbox.

create table app_user (
    id             uuid         not null,
    project_id     uuid         not null,
    email          varchar(254) not null,
    password_hash  varchar(255) not null,
    role           varchar(16)  not null,
    enabled        boolean      not null default true,
    created_at     timestamp with time zone not null,

    constraint pk_app_user primary key (id),
    constraint fk_app_user_project foreign key (project_id) references project (id),
    constraint uq_app_user_project_email unique (project_id, email),
    constraint ck_app_user_email_lowercase check (email = lower(email)),
    constraint ck_app_user_role check (role in ('VIEWER', 'EDITOR', 'ADMIN'))
);

-- Refresh tokens. Only a digest is stored, so a database dump is not a set of live sessions.
--
-- revoked_at is a timestamp rather than a delete, and expired rows are kept: "when did this
-- session stop working" is a question asked after an incident, and a deleted row cannot answer
-- it. Whoever wants them gone can prune on expires_at.

create table refresh_token (
    id            uuid         not null,
    project_id    uuid         not null,
    user_id       uuid         not null,
    token_digest  varchar(64)  not null,
    issued_at     timestamp with time zone not null,
    expires_at    timestamp with time zone not null,
    revoked_at    timestamp with time zone,

    constraint pk_refresh_token primary key (id),
    constraint fk_refresh_token_project foreign key (project_id) references project (id),
    constraint fk_refresh_token_user foreign key (user_id) references app_user (id),
    -- The digest is what a presented token is looked up by, so this index is the read path,
    -- and the uniqueness is what makes "one row or none" true rather than merely likely.
    constraint uq_refresh_token_digest unique (token_digest),
    constraint ck_refresh_token_outlives_issue check (expires_at > issued_at)
);

create index ix_refresh_token_user on refresh_token (project_id, user_id);
