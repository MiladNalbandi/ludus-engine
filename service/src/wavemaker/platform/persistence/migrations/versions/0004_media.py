"""Audio clips and sprites: their metadata, and deliberately not their bytes.

Revision ID: 0004
Revises: 0002

**Written against 0002 on purpose.** Revision 0003 was being written in parallel when this
was, so this one names 0002 as its parent. When both have landed there are two heads; the fix
is to rebase this one onto 0003 by changing `down_revision` to "0003". Nothing here depends on
0003's tables, so the order between them does not matter beyond keeping one line of history.

Carried over from the Java's V5 (audio) and V12 (sprite), with one column added.
"""

from alembic import op

revision = "0004"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The bytes live outside the database, behind the platform's blob store, and these tables
    # hold only what is needed to list, name and serve them. That separation is the whole
    # design: an author opening a dropdown of forty clips runs one query over a few kilobytes
    # and never touches forty files. Bytes in a bytea column here would make that query read
    # megabytes per row unless every caller remembered to select columns — and one that forgot
    # would be slow rather than broken, which is the kind of mistake that survives review.
    #
    # size_bytes is what the store actually wrote, not a length the client declared, and it is
    # never zero: an empty upload is refused before a row exists.
    #
    # content_sha256 is new. It is the ETag a client revalidates with, computed while the
    # upload streams to disk, so serving a 304 never means opening the file.
    #
    # Two tables rather than one with a kind column, as in the Java. Audio and sprites are two
    # catalogues to every caller, and a list of clips should not scan item art to find them.
    for table in ("audio_clip", "sprite"):
        op.execute(f"""
            create table {table} (
                id              uuid         not null,
                project_id      uuid         not null,
                filename        varchar(255) not null,
                content_type    varchar(128) not null,
                size_bytes      bigint       not null,
                content_sha256  char(64)     not null,
                created_at      timestamptz  not null,

                constraint pk_{table} primary key (id),
                constraint fk_{table}_project foreign key (project_id)
                    references project (id) on delete cascade,
                constraint ck_{table}_has_bytes check (size_bytes > 0),
                constraint ck_{table}_sha256 check (content_sha256 ~ '^[0-9a-f]{{64}}$')
            )
        """)
        # The list is newest first, per project, and that is the only query that scans.
        op.execute(f"create index ix_{table}_project on {table} (project_id, created_at desc)")

    # A sprite is not referenced by a foreign key from anywhere, and that is a decision rather
    # than an oversight: an item's sprite reference is an opaque string the game resolves, so a
    # project that serves its art from a CDN puts a URL there and never uploads anything. A
    # foreign key would make this service the only possible source of item art.


def downgrade() -> None:
    op.execute("drop table if exists sprite")
    op.execute("drop table if exists audio_clip")
