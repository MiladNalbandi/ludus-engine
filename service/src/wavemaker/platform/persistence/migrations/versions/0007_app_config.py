"""Application configuration: the settings a game client reads at launch.

Revision ID: 0007
Revises: 0006m

Carried over from the Java's V7 and V7.1, which R1 did not bring across. The frozen contract
has served `/api/v1/admin/app-config` and `/api/v1/public/app-config` since 1.0.0, so a
client built against it calls them on every launch; R9 found them missing while walking the
whole contract against this service.

One row per project, and the primary key says so. Configuration is singular: there is not a
list of configurations one of which is current, and a table that allowed two would need a rule
somewhere choosing between them.

The same column pair as `wave`, for the same reason: the document is stored verbatim so the
ETag over its bytes is stable, and the generated `jsonb` column exists only to be queried.
"""

from alembic import op

revision = "0007"
down_revision = "0006m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        create table app_config (
            project_id   uuid        not null,
            config_json  text        not null,
            config       jsonb generated always as (config_json::jsonb) stored,
            updated_at   timestamptz not null,

            constraint pk_app_config primary key (project_id),
            constraint fk_app_config_project foreign key (project_id)
                references project (id) on delete cascade
        )
    """)


def downgrade() -> None:
    op.execute("drop table if exists app_config")
