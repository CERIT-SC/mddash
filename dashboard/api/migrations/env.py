import logging

from alembic import context

logger = logging.getLogger("alembic.env")


def run_migrations_online() -> None:
    """Run migrations on the connection handed over by `db.run_migrations`."""
    connection = context.config.attributes["connection"]
    context.configure(connection=connection, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if not context.is_offline_mode():
    run_migrations_online()
