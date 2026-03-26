import logging

from alembic import context
from flask import current_app

config = context.config

logger = logging.getLogger("alembic.env")

target_metadata = current_app.extensions["migrate"].db.metadata


def run_migrations_online():
    """Run migrations in 'online' mode with a database connection."""
    connectable = current_app.extensions["migrate"].db.engine

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
