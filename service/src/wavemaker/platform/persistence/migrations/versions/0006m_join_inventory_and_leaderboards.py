"""Join the inventory and leaderboards migrations into one history.

Revision ID: 0006m
Revises: 0005, 0006

R4 (inventory, 0005) and R6 (leaderboards and progression, 0006) were built in parallel, each on
top of 0004m, so the history forked into two heads again. Like 0004m, this revision changes
nothing in the database — the two branches touch disjoint tables — and only records that both
have run, so Alembic has one head to upgrade to.

A written migration is treated as immutable here, so the fork is joined rather than either side
being rewritten to sit on the other.
"""

revision = "0006m"
down_revision = ("0005", "0006")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
