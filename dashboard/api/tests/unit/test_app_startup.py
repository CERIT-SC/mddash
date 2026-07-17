"""Tests for dashboard API startup behavior."""

import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from flask import Flask
from pytest_mock import MockerFixture


def _fresh_import_app(tmp_path: Path, monkeypatch, mocker: MockerFixture) -> ModuleType:  # ruff:ignore[missing-type-function-argument]
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JUPYTERHUB_USER", "testuser")
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/testuser")
    monkeypatch.setenv("POD_NAMESPACE", "test-namespace")
    monkeypatch.setenv("HUB_NAMESPACE", "hub-namespace")
    monkeypatch.setenv("PVC_NAME", "test-pvc")
    monkeypatch.setenv("PVC_STORAGE_SIZE", "1Gi")
    monkeypatch.setenv("TUNER_USER", "tuner")
    monkeypatch.setenv("TUNER_PASSWORD", "secret")

    sys.modules.pop("app", None)
    mocker.patch("kubernetes.config.load_incluster_config")
    mocker.patch("kubernetes.client.CoreV1Api")
    mocker.patch("kubernetes.client.BatchV1Api")
    return importlib.import_module("app")


def test_importing_app_module_does_not_run_migrations(tmp_path: Path, monkeypatch, mocker: MockerFixture) -> None:  # ruff:ignore[missing-type-function-argument]
    """Gunicorn factory imports should not construct the Flask app eagerly."""
    upgrade = mocker.patch("flask_migrate.upgrade")

    app_module = _fresh_import_app(tmp_path, monkeypatch, mocker)

    assert hasattr(app_module, "create_app")
    assert not hasattr(app_module, "app")
    upgrade.assert_not_called()


def test_run_migrations_skips_upgrade_when_database_is_at_head(app: Flask, mocker: MockerFixture) -> None:
    """Already-current databases should avoid full Alembic upgrade machinery."""
    import app as app_module  # ruff:ignore[import-outside-top-level]

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = "006"
    script = MagicMock()
    script.get_current_head.return_value = "006"

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    upgrade = mocker.patch("app.upgrade")
    stamp = mocker.patch("app.stamp")
    inspect_db = mocker.patch("app.sa_inspect")

    with app.app_context():
        app_module._run_migrations()  # ruff:ignore[private-member-access]

    upgrade.assert_not_called()
    stamp.assert_not_called()
    inspect_db.assert_not_called()


def test_run_migrations_upgrades_when_database_is_behind_head(app: Flask, mocker: MockerFixture) -> None:
    """Behind-head databases must still be upgraded before serving requests."""
    import app as app_module  # ruff:ignore[import-outside-top-level]

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = "005"
    script = MagicMock()
    script.get_current_head.return_value = "006"
    script.get_revision.return_value = MagicMock()

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    upgrade = mocker.patch("app.upgrade")
    stamp = mocker.patch("app.stamp")

    with app.app_context():
        app_module._run_migrations()  # ruff:ignore[private-member-access]

    stamp.assert_not_called()
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))


def test_run_migrations_stamps_unversioned_database_with_tables(app: Flask, mocker: MockerFixture) -> None:
    """Legacy unversioned DBs with existing tables keep baseline stamping behavior."""
    import app as app_module  # ruff:ignore[import-outside-top-level]

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = None
    script = MagicMock()
    script.get_current_head.return_value = "006"
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["experiments"]

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    mocker.patch("app.sa_inspect", return_value=inspector)
    stamp = mocker.patch("app.stamp")
    upgrade = mocker.patch("app.upgrade")

    with app.app_context():
        app_module._run_migrations()  # ruff:ignore[private-member-access]

    stamp.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR), revision="001", purge=True)
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))


def test_run_migrations_restamps_unknown_revision(app: Flask, mocker: MockerFixture) -> None:
    """Unknown DB revisions ahead of the script directory must fail fast."""
    import app as app_module  # ruff:ignore[import-outside-top-level]
    from alembic.util.exc import CommandError  # ruff:ignore[import-outside-top-level]

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = "old-rev"
    script = MagicMock()
    script.get_current_head.return_value = "006"
    script.get_revision.side_effect = CommandError("unknown revision")

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    stamp = mocker.patch("app.stamp")
    upgrade = mocker.patch("app.upgrade")

    with (
        app.app_context(),
        pytest.raises(RuntimeError, match="ahead of migration scripts"),
    ):
        app_module._run_migrations()  # ruff:ignore[private-member-access]

    stamp.assert_not_called()
    upgrade.assert_not_called()


def test_run_migrations_upgrades_fresh_empty_database(app: Flask, mocker: MockerFixture) -> None:
    """Brand-new empty databases should go straight to upgrade without stamping."""
    import app as app_module  # ruff:ignore[import-outside-top-level]

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = None
    script = MagicMock()
    script.get_current_head.return_value = "006"
    inspector = MagicMock()
    inspector.get_table_names.return_value = []

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    mocker.patch("app.sa_inspect", return_value=inspector)
    stamp = mocker.patch("app.stamp")
    upgrade = mocker.patch("app.upgrade")

    with app.app_context():
        app_module._run_migrations()  # ruff:ignore[private-member-access]

    stamp.assert_not_called()
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))
