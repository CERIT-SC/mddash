"""Tests for dashboard API startup behavior."""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import db
import pytest
from alembic.util.exc import CommandError
from pytest_mock import MockerFixture


def test_importing_app_module_does_not_build_the_app(mocker: MockerFixture) -> None:
    """The uvicorn factory import must not construct the app or touch the database."""
    run_migrations = mocker.patch("db.run_migrations")
    sys.modules.pop("app", None)

    app_module = importlib.import_module("app")

    assert hasattr(app_module, "create_app")
    assert not hasattr(app_module, "app")
    run_migrations.assert_not_called()


async def test_lifespan_migrates_before_serving(tmp_path: Path, mocker: MockerFixture) -> None:
    """Startup validates the catalog, migrates the DB file under DATA_DIR, and binds the engine to it."""
    import app as app_module

    order: list[str] = []
    mocker.patch("app.load_catalog_or_exit", side_effect=lambda: order.append("catalog"))
    run_migrations = mocker.patch("app.run_migrations", side_effect=lambda _path: order.append("migrate"))
    mocker.patch("app.du_monitor", AsyncMock())
    init_engine = mocker.patch("app.init_engine")
    mocker.patch("app.dispose_engine", AsyncMock())

    application = app_module.create_app()
    async with application.router.lifespan_context(application):
        assert order == ["catalog", "migrate"]
        run_migrations.assert_called_once_with(tmp_path / "experiments.db")
        init_engine.assert_called_once_with(tmp_path / "experiments.db")


def _patch_alembic(
    mocker: MockerFixture, current: str | None, head: str = "006", tables: list[str] | None = None
) -> tuple:
    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = current
    script = MagicMock()
    script.get_current_head.return_value = head
    inspector = MagicMock()
    inspector.get_table_names.return_value = tables or []
    mocker.patch("db.MigrationContext.configure", return_value=migration_context)
    mocker.patch("db.ScriptDirectory", return_value=script)
    inspect_db = mocker.patch("db.sa_inspect", return_value=inspector)
    return script, inspect_db, mocker.patch("db.command.stamp"), mocker.patch("db.command.upgrade")


def test_run_migrations_skips_upgrade_when_database_is_at_head(tmp_path: Path, mocker: MockerFixture) -> None:
    """Already-current databases should avoid full Alembic upgrade machinery."""
    _, inspect_db, stamp, upgrade = _patch_alembic(mocker, current="006")

    db.run_migrations(tmp_path / "test.db")

    upgrade.assert_not_called()
    stamp.assert_not_called()
    inspect_db.assert_not_called()


def test_run_migrations_upgrades_when_database_is_behind_head(tmp_path: Path, mocker: MockerFixture) -> None:
    """Behind-head databases must still be upgraded before serving requests."""
    _, _, stamp, upgrade = _patch_alembic(mocker, current="005")

    db.run_migrations(tmp_path / "test.db")

    stamp.assert_not_called()
    upgrade.assert_called_once()
    assert upgrade.call_args.args[1] == "head"


def test_run_migrations_stamps_unversioned_database_with_tables(tmp_path: Path, mocker: MockerFixture) -> None:
    """Legacy unversioned DBs with existing tables keep baseline stamping behavior."""
    _, _, stamp, upgrade = _patch_alembic(mocker, current=None, tables=["experiments"])

    db.run_migrations(tmp_path / "test.db")

    stamp.assert_called_once()
    assert stamp.call_args.args[1] == "001"
    assert stamp.call_args.kwargs == {"purge": True}
    upgrade.assert_called_once()


def test_run_migrations_rejects_unknown_revision(tmp_path: Path, mocker: MockerFixture) -> None:
    """Unknown DB revisions ahead of the script directory must fail fast."""
    script, _, stamp, upgrade = _patch_alembic(mocker, current="old-rev")
    script.get_revision.side_effect = CommandError("unknown revision")

    with pytest.raises(RuntimeError, match="ahead of migration scripts"):
        db.run_migrations(tmp_path / "test.db")

    stamp.assert_not_called()
    upgrade.assert_not_called()


def test_run_migrations_upgrades_fresh_empty_database(tmp_path: Path, mocker: MockerFixture) -> None:
    """Brand-new empty databases should go straight to upgrade without stamping."""
    _, _, stamp, upgrade = _patch_alembic(mocker, current=None, tables=[])

    db.run_migrations(tmp_path / "test.db")

    stamp.assert_not_called()
    upgrade.assert_called_once()


def test_run_migrations_creates_schema_on_real_database(tmp_path: Path) -> None:
    """End to end: a fresh file reaches head and a second run is a no-op."""
    db_path = tmp_path / "real.db"
    db.run_migrations(db_path)
    db.run_migrations(db_path)

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"experiments", "notebooks", "simulation_jobs", "alembic_version"} <= tables
