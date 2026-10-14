"""Async SQLAlchemy engine/session management and Alembic migrations."""

import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    # Models carry transient (unmapped) state filled by their async refresh step.
    __allow_unmapped__ = True


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(db_path: Path) -> AsyncEngine:
    """(Re)bind the process-wide async engine to a SQLite file."""
    global _engine, _sessionmaker  # ruff:ignore[global-statement]
    _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    # Objects stay readable after commit: response serialization runs after the final commit.
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    """Close all pooled connections."""
    if _engine is not None:
        await _engine.dispose()


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the sessionmaker bound by `init_engine`."""
    if _sessionmaker is None:
        raise RuntimeError("Database engine is not initialized.")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Provide one session per request (FastAPI dependency); uncommitted work rolls back on close.

    Yields:
        The request's session.
    """
    session = session_factory()()
    try:
        yield session
    finally:
        await session.close()


def _alembic_config(connection: object) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.attributes["connection"] = connection
    return cfg


def _log_duration(phase: str, start: float) -> None:
    logger.info("startup phase %s completed in %.3fs", phase, time.perf_counter() - start)


def run_migrations(db_path: Path, revision: str = "head") -> None:
    """
    Bring the database to `revision` (sync; run before serving requests).

    Unversioned databases that already hold tables are stamped at the 001 baseline first.

    Raises:
        RuntimeError: If the database revision is ahead of the migration scripts.
    """
    start = time.perf_counter()
    logger.info("Checking database migrations...")
    script = ScriptDirectory(str(MIGRATIONS_DIR))
    head_rev = script.get_current_head()
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            current_rev = MigrationContext.configure(conn).get_current_revision()
            if current_rev is None:
                if sa_inspect(conn).get_table_names():
                    logger.info("Unversioned DB with tables; stamping to migration baseline...")
                    command.stamp(_alembic_config(conn), "001", purge=True)
                    current_rev = "001"
            else:
                try:
                    script.get_revision(current_rev)
                except CommandError:
                    logger.error(
                        "DB revision '%s' not in migration scripts (head: '%s'). Downgrade the DB first.",
                        current_rev,
                        head_rev,
                    )
                    raise RuntimeError(f"DB revision '{current_rev}' is ahead of migration scripts.")
            _log_duration("db-revision-check", start)

            target = head_rev if revision == "head" else revision
            if current_rev == target:
                logger.info("Database is at migration %s; skipping upgrade", target)
                return

            start = time.perf_counter()
            logger.info("Running database migrations...")
            command.upgrade(_alembic_config(conn), revision)
            _log_duration("migration-upgrade", start)
    finally:
        engine.dispose()
