"""Leaderboards, and how far a player has come.

Revision ID: 0006
Revises: 0004m

Carried over from the Java's V9 (the XP curve and a player's XP) and V11 (boards and scores),
under each app's own table prefix: `leaderboard_*` and `progression_*`.

R4 (inventory) is being written in parallel as 0005, also on top of 0004m, so the history will
fork into two heads again. As with 0004m, the maintainer joins them with a merge revision that
changes nothing in the database; the tables here and inventory's are disjoint. Neither this
file nor 0005 should be edited to sit on the other.

Every table carries `project_id` with a foreign key to `project`, and every per-player table
points at `player (id, project_id)`, so a score or an XP total cannot belong to a different
project from its player. The keys of the per-player tables lead with `project_id` as well. The
economy's key is `(player_id, currency)`, which let an upsert from one project conflict with —
and, without an extra `where`, add to — another project's row; a key that includes the project
cannot conflict across projects at all.
"""

from alembic import op

revision = "0006"
down_revision = "0004m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A board the project defines. The service does not know what "time_trial" means: it sorts
    # numbers and the board says which way. `descending` belongs to the board rather than to a
    # query, so two callers cannot disagree about a player's rank.
    op.execute("""
        create table leaderboard_board (
            project_id  uuid         not null,
            board_id    varchar(64)  not null,
            name        varchar(255) not null,
            descending  boolean      not null default true,
            created_at  timestamptz  not null,
            updated_at  timestamptz  not null,

            constraint pk_leaderboard_board primary key (project_id, board_id),
            constraint fk_leaderboard_board_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint ck_leaderboard_board_id check (board_id ~ '^[a-z0-9_]+$'),
            constraint ck_leaderboard_board_name_not_blank check (length(trim(name)) > 0)
        )
    """)

    # One score per player per board. A board that kept several would need a rule for which
    # one ranks, and every reader would have to know it.
    op.execute("""
        create table leaderboard_entry (
            project_id  uuid        not null,
            board_id    varchar(64) not null,
            player_id   uuid        not null,
            score       bigint      not null,
            updated_at  timestamptz not null,

            constraint pk_leaderboard_entry primary key (project_id, board_id, player_id),
            constraint fk_leaderboard_entry_project foreign key (project_id)
                references project (id) on delete cascade,
            -- A board's scores go with it.
            constraint fk_leaderboard_entry_board foreign key (project_id, board_id)
                references leaderboard_board (project_id, board_id) on delete cascade,
            -- And a player's with them. A submission naming a player who is not in this
            -- project fails here, in the same statement, with no lookup in front to race.
            constraint fk_leaderboard_entry_player foreign key (player_id, project_id)
                references player (id, project_id) on delete cascade
        )
    """)
    # The index every page and every rank runs on. `player_id` is in it, and that is the whole
    # reason paging works: scores tie constantly, an order by score alone is not total, and a
    # keyset cursor over an order that is not total skips and repeats rows at every tie.
    #
    # One index serves both directions. The Java built a second one in descending order, but a
    # B-tree is read backwards as cheaply as forwards, and (score desc, player_id desc) is
    # exactly this index read from the other end.
    op.execute("""
        create index ix_leaderboard_entry_rank
            on leaderboard_entry (project_id, board_id, score, player_id)
    """)

    # The project's XP curve, as data rather than code, so a game with a different ramp does
    # not need a fork. `xp_required` is cumulative: "how far to the next stage" is then a
    # subtraction, not a running sum over every earlier row.
    op.execute("""
        create table progression_stage (
            project_id   uuid         not null,
            stage        integer      not null,
            xp_required  bigint       not null,
            label        varchar(120),

            constraint pk_progression_stage primary key (project_id, stage),
            constraint fk_progression_stage_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint ck_progression_stage_not_negative
                check (stage >= 0 and xp_required >= 0),
            -- Two stages beginning at the same total would make "which stage is this" a guess.
            constraint uq_progression_stage_threshold unique (project_id, xp_required)
        )
    """)

    # A player's XP. There is no stage column: the stage is derived from this and the curve,
    # and a stored one would be a second truth that goes stale, for every player at once, the
    # moment somebody edits the curve.
    op.execute("""
        create table progression_xp (
            project_id  uuid        not null,
            player_id   uuid        not null,
            xp          bigint      not null,
            updated_at  timestamptz not null,

            constraint pk_progression_xp primary key (project_id, player_id),
            constraint fk_progression_xp_project foreign key (project_id)
                references project (id) on delete cascade,
            constraint fk_progression_xp_player foreign key (player_id, project_id)
                references player (id, project_id) on delete cascade,
            constraint ck_progression_xp_not_negative check (xp >= 0)
        )
    """)


def downgrade() -> None:
    op.execute("drop table if exists progression_xp")
    op.execute("drop table if exists progression_stage")
    op.execute("drop table if exists leaderboard_entry")
    op.execute("drop table if exists leaderboard_board")
