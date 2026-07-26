"""Alembic migration environment — connects to SQLite via api.config.DB_PATH."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the project root is on sys.path so api.* imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import DB_PATH
from api.db.models import Base

alembic_cfg = context.config
if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _db_url() -> str:
    return f"sqlite:///{DB_PATH}"


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = alembic_cfg.get_section(alembic_cfg.config_ini_section, {})
    cfg["sqlalchemy.url"] = _db_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
