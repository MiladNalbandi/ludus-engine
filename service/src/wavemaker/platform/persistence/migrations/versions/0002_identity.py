"""Accounts, and the sessions they open.

Revision ID: 0002
Revises: 0001

Carried over from the Java's V2, including the two decisions worth keeping.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The unique constraint is on (project_id, email) rather than on email: two projects may
    # each have an account with the same address, and they are different people as far as this
    # engine is concerned.
    #
    # Addresses are stored already lower-cased by the application. The check refuses anything
    # else rather than folding case itself, so a value written by something other than the
    # application cannot create a second account for the same mailbox.
    op.execute("""
        create table account (
            id             uuid         not null,
            project_id     uuid         not null,
            email          varchar(254) not null,
            password_hash  varchar(255) not null,
            role           varchar(16)  not null,
            enabled        boolean      not null default true,
            created_at     timestamptz  not null,

            constraint pk_account primary key (id),
            constraint fk_account_project foreign key (project_id) references project (id),
            constraint uq_account_project_email unique (project_id, email),
            constraint ck_account_email_lowercase check (email = lower(email)),
            constraint ck_account_role check (role in ('VIEWER', 'EDITOR', 'ADMIN'))
        )
    """)

    # Only a digest is stored, so a database dump is not a set of live sessions.
    #
    # `revoked_at` is a timestamp rather than a delete, and expired rows are kept: "when did
    # this session stop working" is a question asked after an incident, and a deleted row
    # cannot answer it.
    op.execute("""
        create table refresh_token (
            id            uuid        not null,
            project_id    uuid        not null,
            account_id    uuid        not null,
            token_digest  varchar(64) not null,
            issued_at     timestamptz not null,
            expires_at    timestamptz not null,
            revoked_at    timestamptz,

            constraint pk_refresh_token primary key (id),
            constraint fk_refresh_token_project foreign key (project_id)
                references project (id),
            constraint fk_refresh_token_account foreign key (account_id)
                references account (id) on delete cascade,
            -- The digest is what a presented token is looked up by, so this is the read path,
            -- and the uniqueness makes "one row or none" true rather than merely likely.
            constraint uq_refresh_token_digest unique (token_digest),
            constraint ck_refresh_token_outlives_issue check (expires_at > issued_at)
        )
    """)
    op.execute("create index ix_refresh_token_account on refresh_token (project_id, account_id)")


def downgrade() -> None:
    op.execute("drop table if exists refresh_token")
    op.execute("drop table if exists account")
