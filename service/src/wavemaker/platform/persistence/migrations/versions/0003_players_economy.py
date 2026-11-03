"""API keys, players, and what players hold.

Revision ID: 0003
Revises: 0002

Carried over from the Java's V3, V8 and V9. Two of the three tables belong to the platform —
a key and a player are identity, and every player-facing app needs them — and one belongs to
the economy app, which is why it carries the app's name as a prefix.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # What a game client holds. Only a digest is stored, so a database dump is not a set of
    # keys anybody can use.
    #
    # The prefix is the first few characters of the key and is not secret: it is how a person
    # tells two keys apart in a list without being shown either. A presented key is looked up by
    # its digest, which is unique, so a lookup is one indexed equality with nothing to resolve.
    #
    # `revoked_at` is a timestamp rather than a delete. "When did this key stop working" is a
    # question asked after an incident, and a deleted row cannot answer it.
    op.execute("""
        create table api_key (
            id             uuid         not null,
            project_id     uuid         not null,
            name           varchar(120) not null,
            prefix         varchar(16)  not null,
            secret_digest  varchar(64)  not null,
            role           varchar(16)  not null,
            created_at     timestamptz  not null,
            revoked_at     timestamptz,

            constraint pk_api_key primary key (id),
            constraint fk_api_key_project foreign key (project_id) references project (id),
            constraint uq_api_key_digest unique (secret_digest),
            -- A key ships inside a binary anybody can unpack, so anything a key can do should
            -- be assumed public. A key that could write is a key that can be lifted out of the
            -- game and used to write. Widening this is a migration and a decision, not a value
            -- somebody can set.
            constraint ck_api_key_role check (role in ('VIEWER')),
            constraint ck_api_key_revoked_after_creation
                check (revoked_at is null or revoked_at >= created_at)
        )
    """)
    op.execute("create index ix_api_key_project on api_key (project_id, created_at)")

    # Who is playing. The service does not know what a player *is*: it stores an identifier the
    # game already has — a device id, a platform account id — and never interprets it. Anything
    # else means owning player accounts, with the password resets and deletion requests that
    # come with them, for a game that already has an identity system or chose not to.
    op.execute("""
        create table player (
            id            uuid         not null,
            project_id    uuid         not null,
            external_id   varchar(190) not null,
            -- Set by the player, and not unique: two people may both be "Alex", and enforcing
            -- otherwise means telling somebody their name is taken.
            display_name  varchar(120),
            created_at    timestamptz  not null,
            -- Moved on every session. It is what answers "who played last week" without an
            -- events table.
            last_seen_at  timestamptz  not null,

            constraint pk_player primary key (id),
            constraint fk_player_project foreign key (project_id)
                references project (id) on delete cascade,
            -- One row per identifier per project. Starting a session is an upsert against this,
            -- so a client retrying through a network blip — or two requests racing on a first
            -- launch — resolve the same player instead of making a second one whose progress
            -- is unreachable.
            constraint uq_player_external_id unique (project_id, external_id),
            -- The key the per-player tables point at, so a balance cannot belong to a
            -- different project from its player.
            constraint uq_player_id_project unique (id, project_id),
            constraint ck_player_external_id_not_blank check (length(trim(external_id)) > 0),
            constraint ck_player_display_name_not_blank
                check (display_name is null or length(trim(display_name)) > 0)
        )
    """)
    op.execute("create index ix_player_last_seen on player (project_id, last_seen_at desc)")

    # One row per player per currency, owned by the economy app.
    #
    # The currency is the project's own word — coins, gems, energy — rather than an enum, which
    # would mean a release of this service every time a game invents one.
    #
    # The balance is only ever changed by one statement with the arithmetic inside it
    # (`amount = amount + ...`), never read, changed in Python and written back: two grants
    # arriving together would both read 100, both write 101, and one would simply be gone.
    op.execute("""
        create table economy_balance (
            project_id  uuid        not null,
            player_id   uuid        not null,
            currency    varchar(40) not null,
            amount      bigint      not null,
            updated_at  timestamptz not null,

            constraint pk_economy_balance primary key (player_id, currency),
            constraint fk_economy_balance_project foreign key (project_id)
                references project (id) on delete cascade,
            -- Composite, so a balance cannot belong to a different project from its player,
            -- and a grant to a player who is not in this project fails here rather than in a
            -- lookup that ran first and could be raced. Removing a player removes their money:
            -- an orphaned balance is money nobody can see or spend.
            constraint fk_economy_balance_player foreign key (player_id, project_id)
                references player (id, project_id) on delete cascade,
            -- The overdraft guard, in the database. A spend subtracts and lets this refuse;
            -- it does not read the balance first. That holds for every code path, including
            -- one written later by somebody who forgot to check — which is the only version
            -- of this rule worth having.
            constraint ck_economy_balance_not_negative check (amount >= 0),
            constraint ck_economy_balance_currency check (currency ~ '^[a-z0-9_]+$')
        )
    """)


def downgrade() -> None:
    op.execute("drop table if exists economy_balance")
    op.execute("drop table if exists player")
    op.execute("drop table if exists api_key")
