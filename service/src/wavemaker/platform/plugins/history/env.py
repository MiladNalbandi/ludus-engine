"""Alembic's entry point for an app's own history.

The platform's, never the app's: an app ships revision files, not the code that runs them. The
runner hands in a connection that is already inside the transaction it will judge, and the
version table that belongs to this app, so nothing here opens a connection or commits.
"""

from alembic import context

context.configure(
    connection=context.config.attributes["connection"],
    version_table=str(context.config.attributes["version_table"]),
)
with context.begin_transaction():
    context.run_migrations()
