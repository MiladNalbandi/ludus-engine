-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Audio metadata. Deliberately not audio bytes.
--
-- The bytes live outside the database, behind AudioStore, and this table holds only what is needed
-- to list, name and serve them. The separation is the whole design: an author opening a dropdown of
-- forty clips runs one query over a few kilobytes, and never touches forty files.
--
-- Putting the bytes in a bytea column here would make that query read megabytes per row unless
-- every caller remembered to select columns explicitly -- and one that forgot would be slow rather
-- than broken, which is the kind of mistake that survives review and shows up as a bill.
--
-- size_bytes is what the store actually wrote, not a length the client declared.

create table audio_clip (
    id            uuid         not null,
    project_id    uuid         not null,
    filename      varchar(255) not null,
    content_type  varchar(128) not null,
    size_bytes    bigint       not null,
    created_at    timestamp with time zone not null,

    constraint pk_audio_clip primary key (id),
    constraint fk_audio_clip_project foreign key (project_id) references project (id) on delete cascade,
    constraint ck_audio_clip_has_bytes check (size_bytes > 0)
);

create index ix_audio_clip_project on audio_clip (project_id, created_at desc);
