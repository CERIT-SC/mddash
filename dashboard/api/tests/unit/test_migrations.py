"""Verify all migrations produce a schema matching the SQLAlchemy models."""

from collections.abc import Mapping
from pathlib import Path

import app as app_module
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from extensions import db, ma, migrate
from flask import Flask
from flask_migrate import upgrade
from sqlalchemy import Engine
from sqlalchemy import inspect as sa_inspect


def _make_app(db_path: Path) -> Flask:
    test_app = Flask(__name__)
    test_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(test_app)
    ma.init_app(test_app)
    migrate.init_app(test_app, db, directory=str(app_module.MIGRATIONS_DIR))
    return test_app


def _column_names(engine: Engine, table: str) -> set[str]:
    return {col["name"] for col in sa_inspect(engine).get_columns(table)}


def _columns(engine: Engine, table: str) -> dict[str, Mapping]:
    return {col["name"]: col for col in sa_inspect(engine).get_columns(table)}


def _upgrade_to(app: Flask, revision: str) -> None:
    with app.app_context():
        upgrade(directory=str(app_module.MIGRATIONS_DIR), revision=revision)


def _table_names(engine: Engine) -> set[str]:
    return set(sa_inspect(engine).get_table_names())


def test_migration_001_creates_initial_schema(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "001")
    with app.app_context():
        engine = db.engine
        assert {"experiments", "notebooks", "gromacs_jobs", "tuner_jobs", "analysis_jobs"}.issubset(
            _table_names(engine)
        )
        assert _column_names(engine, "experiments") == {
            "id",
            "created_at",
            "updated_at",
            "name",
            "source_message",
            "notebooks_repo",
            "mdrepo_id",
            "mdrepo_published",
        }
        assert _column_names(engine, "notebooks") == {"id", "experiment_id", "token"}
        assert _column_names(engine, "gromacs_jobs") == {
            "id",
            "experiment_id",
            "created_at",
            "tpr_name",
            "pme",
            "nb",
            "np",
            "ntomp",
            "extra_args",
            "start_timestamp",
            "finish_timestamp",
            "nsteps",
            "performance",
            "last_known_status",
        }
        assert _column_names(engine, "tuner_jobs") == {
            "id",
            "experiment_id",
            "tpr_name",
            "error_message",
            "created_at",
            "is_stopped",
            "preserved_trials",
        }
        assert _column_names(engine, "analysis_jobs") == {
            "id",
            "experiment_id",
            "created_at",
            "analysis_name",
            "structure_file",
            "trajectory_file",
            "topology_file",
            "last_known_status",
        }


def test_migration_002_adds_notebook_tier_and_gpu(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "002")
    with app.app_context():
        cols = _columns(db.engine, "notebooks")
        assert "tier" in cols
        assert "gpu" in cols
        assert cols["gpu"]["nullable"] is False


def test_migration_003_creates_jti_and_amber(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "003")
    with app.app_context():
        engine = db.engine
        assert "simulation_jobs" in _table_names(engine)
        assert "amber_jobs" in _table_names(engine)
        assert _column_names(engine, "simulation_jobs") == {
            "id",
            "experiment_id",
            "created_at",
            "engine",
            "np",
            "ntomp",
            "extra_args",
            "start_timestamp",
            "finish_timestamp",
            "nsteps",
            "performance",
            "last_known_status",
        }
        assert _column_names(engine, "amber_jobs") == {
            "id",
            "prmtop_name",
            "inpcrd_name",
            "mdin_name",
            "binary",
            "ewald",
        }
        assert _column_names(engine, "gromacs_jobs") == {"id", "tpr_name", "pme", "nb"}
        assert "engine" in _column_names(engine, "experiments")
        assert "inpcrd_name" in _column_names(engine, "tuner_jobs")
        assert "mdin_name" in _column_names(engine, "tuner_jobs")


def test_migration_004_makes_structure_file_nullable(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "004")
    with app.app_context():
        cols = _columns(db.engine, "analysis_jobs")
        assert cols["structure_file"]["nullable"] is True


def test_migration_005_adds_init_step(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "005")
    with app.app_context():
        assert "init_step" in _column_names(db.engine, "gromacs_jobs")


def test_migration_006_renames_tier_enum_values(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "006")
    with app.app_context():
        assert "tier" in _column_names(db.engine, "notebooks")


def test_migration_007_adds_simulation_path_and_drops_file_columns(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "007")
    with app.app_context():
        engine = db.engine
        sim_cols = _columns(engine, "simulation_jobs")
        assert "simulation_path" in sim_cols
        assert sim_cols["simulation_path"]["nullable"] is False
        assert "extra_args" not in sim_cols

        tuner_cols = _columns(engine, "tuner_jobs")
        assert "simulation_path" in tuner_cols
        assert tuner_cols["simulation_path"]["nullable"] is False
        assert "tpr_name" not in tuner_cols
        assert "inpcrd_name" not in tuner_cols
        assert "mdin_name" not in tuner_cols

        assert "tpr_name" not in _column_names(engine, "gromacs_jobs")
        amber_cols = _column_names(engine, "amber_jobs")
        assert "prmtop_name" not in amber_cols
        assert "inpcrd_name" not in amber_cols
        assert "mdin_name" not in amber_cols


def test_migration_008_adds_simulation_path_to_analysis(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "008")
    with app.app_context():
        cols = _columns(db.engine, "analysis_jobs")
        assert "simulation_path" in cols
        assert cols["simulation_path"]["nullable"] is False


def test_migration_010_adds_structured_source_columns(tmp_path: Path) -> None:
    """Source columns are added empty; migrated rows must load through the ORM (enum names, not values)."""
    import sqlalchemy as sa
    from models.experiment import Experiment

    app = _make_app(tmp_path / "test.db")
    _upgrade_to(app, "009")
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO experiments (id, created_at, updated_at, name, source_message) VALUES "
                "('pdbid', '2026-01-01', '2026-01-01', 'a', \"Created by downloading '1LYZ' from RCSB PDB.\"), "
                "('pdburl', '2026-01-01', '2026-01-01', 'b', \"Created by downloading PDB file from 'https://x.org/y.pdb'.\"), "
                "('repo', '2026-01-01', '2026-01-01', 'c', \"Created by downloading repository from 'https://zenodo.org/records/1'.\"), "
                "('upload', '2026-01-01', '2026-01-01', 'd', 'Created by uploading files: a.tpr, b.pdb.'), "
                "('junk', '2026-01-01', '2026-01-01', 'e', 'Some hand-written note.')"
            )
        )

    _upgrade_to(app, "head")
    with app.app_context():
        cols = _column_names(db.engine, "experiments")
        assert {"module_name", "source_type", "source_ref", "source_files"} <= cols
        assert "source_label" not in cols
        assert "source_message" not in cols
        with db.engine.connect() as conn:
            backfilled = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM experiments WHERE "
                    "source_type IS NOT NULL OR source_ref IS NOT NULL OR source_files IS NOT NULL"
                )
            ).scalar_one()
        assert backfilled == 0
        # crashes with LookupError if any stored source_type is not an enum name
        assert len(Experiment.query.all()) == 5


def test_all_migrations_reach_head(tmp_path: Path) -> None:
    app = _make_app(tmp_path / "test.db")
    with app.app_context():
        upgrade(directory=str(app_module.MIGRATIONS_DIR))
        script = ScriptDirectory(str(app_module.MIGRATIONS_DIR))
        head_rev = script.get_current_head()
        with db.engine.connect() as conn:
            current_rev = MigrationContext.configure(conn).get_current_revision()
        assert current_rev == head_rev


def test_models_match_migrated_schema(tmp_path: Path) -> None:
    """db.create_all() on a fresh DB must produce the same columns as migrations."""
    migrated_app = _make_app(tmp_path / "migrated.db")
    create_all_app = Flask(__name__)
    create_all_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'create_all.db'}"
    create_all_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(create_all_app)
    ma.init_app(create_all_app)

    with migrated_app.app_context():
        upgrade(directory=str(app_module.MIGRATIONS_DIR))
        migrated_tables = {table: _column_names(db.engine, table) for table in sa_inspect(db.engine).get_table_names()}

    with create_all_app.app_context():
        db.create_all()
        create_all_tables = {
            table: _column_names(db.engine, table) for table in sa_inspect(db.engine).get_table_names()
        }

    model_tables = {t for t in create_all_tables if not t.startswith("alembic")}
    for table in model_tables:
        assert table in migrated_tables, f"Table '{table}' missing from migrations"
        missing = create_all_tables[table] - migrated_tables[table]
        extra = migrated_tables[table] - create_all_tables[table]
        assert not missing, f"Columns in models but not in migrations for '{table}': {missing}"
        assert not extra, f"Columns in migrations but not in models for '{table}': {extra}"
