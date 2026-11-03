"""Join the economy and media migrations into one history.

Revision ID: 0004m
Revises: 0003, 0004

R3 (players and economy, 0003) and R7 (media, 0004) were built in parallel, each on top of
0002, so the history forked into two heads. Alembic refuses to upgrade to "head" while there are
two, which is the right refusal: it cannot know an order nobody chose.

This revision chooses it. It changes nothing in the database — the two branches touch disjoint
tables — it only records that both have run. Editing 0004 to sit on 0003 instead would reach the
same history, but a migration that has been written is treated as immutable here, and this is
the tool Alembic provides for exactly this case.

The id is "0004m", not "0005", because R4 (inventory) is being written in parallel as 0005.
"""

revision = "0004m"
down_revision = ("0003", "0004")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
