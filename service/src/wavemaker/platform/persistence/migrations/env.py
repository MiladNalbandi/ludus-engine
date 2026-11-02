"""Alembic's entry point. Offline mode is not supported: this project migrates a live database."""

from alembic import context
from sqlalchemy import engine_from_config, pool


def run_migrations_online() -> None:
    section = context.config.get_section(context.config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
