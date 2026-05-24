"""Tests for dashboard API startup behavior."""

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from flask import Flask


def _fresh_import_app(tmp_path: Path, monkeypatch, mocker) -> ModuleType:
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


def test_importing_app_module_does_not_run_migrations(tmp_path: Path, monkeypatch, mocker) -> None:
    """Gunicorn factory imports should not construct the Flask app eagerly."""
    upgrade = mocker.patch("flask_migrate.upgrade")

    app_module = _fresh_import_app(tmp_path, monkeypatch, mocker)

    assert hasattr(app_module, "create_app")
    assert not hasattr(app_module, "app")
    upgrade.assert_not_called()


def test_run_migrations_skips_upgrade_when_database_is_at_head(app: Flask, mocker) -> None:
    """Already-current databases should avoid full Alembic upgrade machinery."""
    import app as app_module

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
        app_module._run_migrations()

    upgrade.assert_not_called()
    stamp.assert_not_called()
    inspect_db.assert_not_called()


def test_run_migrations_upgrades_when_database_is_behind_head(app: Flask, mocker) -> None:
    """Behind-head databases must still be upgraded before serving requests."""
    import app as app_module

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
        app_module._run_migrations()

    stamp.assert_not_called()
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))


def test_run_migrations_stamps_unversioned_database_with_tables(app: Flask, mocker) -> None:
    """Legacy unversioned DBs with existing tables keep baseline stamping behavior."""
    import app as app_module

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
        app_module._run_migrations()

    stamp.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR), revision="001", purge=True)
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))


def test_run_migrations_restamps_unknown_revision(app: Flask, mocker) -> None:
    import app as app_module
    from alembic.util.exc import CommandError

    migration_context = MagicMock()
    migration_context.get_current_revision.return_value = "old-rev"
    script = MagicMock()
    script.get_current_head.return_value = "006"
    script.get_revision.side_effect = CommandError("unknown revision")

    mocker.patch("app.MigrationContext.configure", return_value=migration_context)
    mocker.patch("app.ScriptDirectory", return_value=script)
    stamp = mocker.patch("app.stamp")
    upgrade = mocker.patch("app.upgrade")

    with app.app_context():
        app_module._run_migrations()

    stamp.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR), revision="001", purge=True)
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))


def test_run_migrations_upgrades_fresh_empty_database(app: Flask, mocker) -> None:
    import app as app_module

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
        app_module._run_migrations()

    stamp.assert_not_called()
    upgrade.assert_called_once_with(directory=str(app_module.MIGRATIONS_DIR))
