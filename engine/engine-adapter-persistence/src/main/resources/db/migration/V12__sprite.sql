-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Sprite metadata. Deliberately not sprite bytes, for the same reasons as audio_clip: a 2 MB image
-- in a bytea column is read into memory to be served and makes every backup larger.
--
-- An item's sprite_ref points at one of these by id. It is not a foreign key, and that is a
-- decision rather than an oversight: sprite_ref is documented as an opaque reference the game
-- resolves, so a project that serves its art from a CDN puts a URL there and never uploads
-- anything. A foreign key would make Ludus the only possible source of item art.

create table sprite (
    id           uuid         not null,
    project_id   uuid         not null,
    filename     varchar(255) not null,
    content_type varchar(128) not null,
    size_bytes   bigint       not null,
    created_at   timestamp with time zone not null,

    constraint pk_sprite primary key (id),
    constraint fk_sprite_project foreign key (project_id) references project (id) on delete cascade,
    constraint ck_sprite_has_bytes check (size_bytes > 0)
);

create index ix_sprite_project on sprite (project_id, created_at desc);
