import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_migrations_create_current_database_schema() -> None:
    command.upgrade(Config("alembic.ini"), "head")

    with sqlite3.connect(Path(os.environ["TUNER_DB"])) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}

    assert {"alembic_version", "jobs", "trials"} <= tables
    assert revision == ("002",)
    assert "sim_length_ns" in job_columns
