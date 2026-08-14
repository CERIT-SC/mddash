"""Unit tests for the Simulation class."""

import json
import os
import uuid
from pathlib import Path

import pytest
from enums import Engine, JobStatus
from errors import ApiError
from extensions import db
from flask import Flask
from manifest_schema import schema_url
from models import Experiment, Notebook
from models.gromacs_job import GromacsJob
from models.simulation import Simulation
from models.tuner_job import TunerJob
from werkzeug.exceptions import BadRequest

GMX_SCHEMA_URL = schema_url(Engine.GMX)

GMX_FILES = {
    "run_input": "production/protein.tpr",
    "reference_structure": "analysis/protein-reference.gro",
    "trajectory": "production/protein.xtc",
}


def _seed_experiment(app: Flask, exp_id: str = "simts") -> str:
    """
    Seed a minimal experiment into the DB.

    Returns:
        The experiment ID.
    """
    with app.app_context():
        exp = Experiment(id=exp_id, name="Sim Test", source_message="test", notebooks_repo="https://github.com/t/r.git")
        db.session.add(exp)
        db.session.flush()
        nb = Notebook(experiment_id=exp_id)
        db.session.add(nb)
        db.session.commit()
        return exp_id


def _write_sim_file(exp_dir: Path, simulation_path: str, files: dict, name: str = "protein") -> str:
    """
    Write a GMX simulation manifest.

    Returns:
        The simulation_path.
    """
    sim_file = exp_dir / simulation_path
    sim_file.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "$schema": GMX_SCHEMA_URL,
        "name": name,
        "engine": "GMX",
        "files": files,
        "extra_args": "",
    }
    sim_file.write_text(json.dumps(content))
    return simulation_path


class TestDiscovery:
    """Discovery finds .simulation.json anywhere under the experiment directory."""

    def test_finds_simulation_anywhere(self, app: Flask, tmp_path: Path) -> None:
        """Simulations are discovered in nested directories."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {
                "run_input": "production/protein.tpr",
                "reference_structure": "analysis/protein-reference.gro",
                "trajectory": "production/protein.xtc",
            },
        )
        _write_sim_file(
            exp_dir,
            "equilibration/nvt.simulation.json",
            {
                "run_input": "equilibration/nvt.tpr",
                "reference_structure": "analysis/nvt-reference.gro",
                "trajectory": "equilibration/nvt.xtc",
            },
        )

        with app.app_context():
            sims = Simulation.list(exp_id)
            paths = [s.simulation_path for s in sims]
            assert "protein.simulation.json" in paths
            assert "equilibration/nvt.simulation.json" in paths

    def test_sorted_by_path(self, app: Flask, tmp_path: Path) -> None:
        """Discovery results are sorted by path."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "z.simulation.json",
            {"run_input": "z.tpr", "reference_structure": "z-reference.gro", "trajectory": "z.xtc"},
        )
        _write_sim_file(
            exp_dir,
            "a.simulation.json",
            {"run_input": "a.tpr", "reference_structure": "a-reference.gro", "trajectory": "a.xtc"},
        )

        with app.app_context():
            sims = Simulation.list(exp_id)
            assert sims[0].simulation_path == "a.simulation.json"
            assert sims[1].simulation_path == "z.simulation.json"


class TestValidation:
    """Missing $schema target makes simulation invalid."""

    def test_missing_schema_makes_invalid(self, app: Flask, tmp_path: Path) -> None:
        """Missing $schema target invalidates the simulation."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = "protein.simulation.json"
        sim_file = exp_dir / sim_path
        sim_file.parent.mkdir(parents=True, exist_ok=True)
        content = {
            "$schema": "https://example.com/not-allowed.schema.json",
            "name": "protein",
            "engine": "GMX",
            "files": {
                "run_input": "production/protein.tpr",
                "reference_structure": "analysis/protein-reference.gro",
                "trajectory": "production/protein.xtc",
            },
            "extra_args": "",
        }
        sim_file.write_text(json.dumps(content))

        with app.app_context():
            sim = Simulation.get(exp_id, sim_path)
            assert not sim.valid
            assert any("schema" in e.lower() or "missing" in e.lower() for e in sim.errors)

    def test_valid_simulation(self, app: Flask, tmp_path: Path) -> None:
        """A complete simulation with existing files is valid."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {
                "run_input": "production/protein.tpr",
                "reference_structure": "analysis/protein-reference.gro",
                "trajectory": "production/protein.xtc",
            },
        )
        (exp_dir / "production").mkdir(parents=True, exist_ok=True)
        (exp_dir / "production" / "protein.tpr").write_bytes(b"\x00")
        (exp_dir / "analysis" / "protein-reference.gro").parent.mkdir(parents=True, exist_ok=True)
        (exp_dir / "analysis" / "protein-reference.gro").write_text("gro")
        (exp_dir / "production" / "protein.xtc").write_bytes(b"\x00")

        with app.app_context():
            sim = Simulation.get(exp_id, "protein.simulation.json")
            assert sim.valid
            assert sim.missing_files == []

    def test_require_files_can_limit_required_roles(self, app: Flask, tmp_path: Path) -> None:
        """Action validation only requires the roles needed by that action."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {
                "run_input": "production/protein.tpr",
                "reference_structure": "analysis/protein-reference.gro",
                "trajectory": "production/protein.xtc",
            },
        )
        (exp_dir / "production").mkdir(parents=True, exist_ok=True)
        (exp_dir / "production" / "protein.tpr").write_bytes(b"\x00")

        with app.app_context():
            sim = Simulation.get(exp_id, "protein.simulation.json")
            assert sim.missing_files == ["reference_structure", "trajectory"]

            sim.require_files(["run_input"])

            with pytest.raises(BadRequest, match="Missing files for: 'Reference structure', 'Trajectory'"):
                sim.require_files()


class TestLocking:
    """Lock inference from file permissions and job references."""

    def test_readonly_file_without_jobs_is_locked(self, app: Flask, tmp_path: Path) -> None:
        """A read-only file with no jobs is locked by file permissions."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {"run_input": "p.tpr", "reference_structure": "p-reference.gro", "trajectory": "p.xtc"},
        )

        with app.app_context():
            sim = Simulation.get(exp_id, sim_path)
            assert not sim.locked
            sim.mark_readonly()
            assert sim.locked

    def test_writable_unlocked_file_not_locked(self, app: Flask, tmp_path: Path) -> None:
        """A writable file with no jobs is not locked."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {"run_input": "p.tpr", "reference_structure": "p-reference.gro", "trajectory": "p.xtc"},
        )

        with app.app_context():
            sim = Simulation.get(exp_id, sim_path)
            assert not sim.locked


class TestWriteSimulation:
    """Create simulation JSON via Simulation.write."""

    def test_create_simulation(self, app: Flask, tmp_path: Path) -> None:
        """Simulation.write creates a valid manifest at the default path."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with app.app_context():
            sim = Simulation.write(
                exp_id,
                {
                    "name": "protein",
                    "files": {
                        "run_input": "production/protein.tpr",
                        "reference_structure": "analysis/protein-reference.gro",
                        "trajectory": "production/protein.xtc",
                    },
                    "extra_args": "-v",
                },
            )
            assert sim.simulation_path == "protein.simulation.json"
            assert sim.name == "protein"
            assert sim.valid

    def test_create_rejects_existing_simulation_path(self, app: Flask, tmp_path: Path) -> None:
        """Creating a simulation must not silently overwrite an existing manifest."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with app.app_context():
            Simulation.write(
                exp_id,
                {
                    "name": "protein",
                    "files": {
                        "run_input": "production/protein.tpr",
                        "reference_structure": "analysis/protein-reference.gro",
                        "trajectory": "production/protein.xtc",
                    },
                    "extra_args": "",
                },
            )

            with pytest.raises(BadRequest, match="already exists"):
                Simulation.write(
                    exp_id,
                    {
                        "name": "protein",
                        "files": {
                            "run_input": "production/other.tpr",
                            "reference_structure": "analysis/other-reference.gro",
                            "trajectory": "production/other.xtc",
                        },
                        "extra_args": "",
                    },
                )

    def test_create_rejects_invalid_content(self, app: Flask, tmp_path: Path) -> None:
        """Invalid content is rejected before writing."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with app.app_context(), pytest.raises(BadRequest, match="Missing required file role: 'Reference structure'"):
            Simulation.write(
                exp_id,
                {
                    "name": "protein",
                    "files": {"run_input": "production/protein.tpr"},
                    "extra_args": "",
                },
            )

    def test_validation_message_is_human_readable(self, app: Flask, tmp_path: Path) -> None:
        """Regexes and jsonschema wording must not leak into user-facing errors."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with app.app_context(), pytest.raises(BadRequest) as exc_info:
            Simulation.write(
                exp_id,
                {
                    "name": "🙋🏿",
                    "files": {
                        "run_input": "production/protein.tpr",
                        "reference_structure": "analysis/protein-reference.gro",
                        "trajectory": "production/protein.xtc",
                    },
                    "extra_args": "",
                },
            )

        message = str(exc_info.value.description)
        assert "^[A-Za-z" not in message
        assert "unsupported characters" in message


def _set_mtime(path: Path, mtime: float) -> None:
    """Set an explicit mtime for deterministic 'latest simulation' ordering."""
    os.utime(path, (mtime, mtime))


def _add_gmx_job(app: Flask, exp_id: str, simulation_path: str, **kwargs: object) -> None:
    """Persist a GromacsJob for the given simulation."""
    from enums import DeviceType

    with app.app_context():
        job = GromacsJob(
            id=str(uuid.uuid4()),
            experiment_id=exp_id,
            simulation_path=simulation_path,
            np=1,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.CPU,
            **kwargs,
        )
        db.session.add(job)
        db.session.commit()


class TestUniqueName:
    """Simulation names must be unique per experiment — they are the wizard tab identity."""

    def test_create_rejects_duplicate_name(self, app: Flask, tmp_path: Path) -> None:
        """A second manifest with an existing name is rejected with a conflict."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with app.app_context():
            Simulation.write(exp_id, {"name": "protein", "files": GMX_FILES, "extra_args": ""})

            with pytest.raises(ApiError, match="already exists") as exc_info:
                Simulation.write(
                    exp_id,
                    {
                        "name": "protein",
                        "simulation_path": "other.simulation.json",
                        "files": GMX_FILES,
                        "extra_args": "",
                    },
                )

            assert exc_info.value.code == 409
            assert exc_info.value.problem_type == "urn:mddash:duplicate-simulation-name"

    def test_update_rejects_duplicate_name(self, app: Flask, tmp_path: Path) -> None:
        """Renaming a manifest to another manifest's name is rejected."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")
        _write_sim_file(exp_dir, "ligand.simulation.json", GMX_FILES, name="ligand")

        with app.app_context(), pytest.raises(ApiError, match="already exists"):
            Simulation.update(exp_id, "ligand.simulation.json", {"name": "protein", "files": GMX_FILES})

    def test_update_allows_keeping_own_name(self, app: Flask, tmp_path: Path) -> None:
        """Updating a manifest without changing its name is fine."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")

        with app.app_context():
            sim = Simulation.update(exp_id, "protein.simulation.json", {"name": "protein", "files": GMX_FILES})
            assert sim.name == "protein"

    def test_reserved_new_name_rejected(self, app: Flask, tmp_path: Path) -> None:
        """`_new` is reserved for the wizard's create tab."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with app.app_context():
            with pytest.raises(ApiError, match="reserved") as exc_info:
                Simulation.write(exp_id, {"name": "_new", "files": GMX_FILES, "extra_args": ""})

            assert exc_info.value.code == 409
            assert exc_info.value.problem_type == "urn:mddash:duplicate-simulation-name"

        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")
        with app.app_context(), pytest.raises(ApiError, match="reserved"):
            Simulation.update(exp_id, "protein.simulation.json", {"name": "_new", "files": GMX_FILES})


def _write_two_sims(exp_dir: Path) -> None:
    """Write 'protein' and 'ligand' manifests with protein's mtime older."""
    exp_dir.mkdir(parents=True, exist_ok=True)
    _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")
    _write_sim_file(exp_dir, "ligand.simulation.json", GMX_FILES, name="ligand")
    _set_mtime(exp_dir / "protein.simulation.json", 1_700_000_000)
    _set_mtime(exp_dir / "ligand.simulation.json", 1_700_100_000)


class TestStepStatus:
    """Per-simulation ladder: each manifest infers its own step from its own jobs."""

    def setup_method(self) -> None:
        """Clear the step status cache before each test."""
        from cache import step_status_cache

        step_status_cache.clear()

    def teardown_method(self) -> None:
        """Clear the step status cache after each test."""
        from cache import step_status_cache

        step_status_cache.clear()

    def test_valid_manifest_without_jobs_is_setup_complete(self, app: Flask, tmp_path: Path) -> None:
        """A valid manifest with no jobs sits at step 1."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        with app.app_context():
            sim = Simulation.get(exp_id, "protein.simulation.json")
            assert sim.step == 1
            assert sim.status == "setup complete"
            assert sim.to_dict()["step"] == 1

    def test_invalid_manifest_is_setup(self, app: Flask, tmp_path: Path) -> None:
        """An invalid manifest sits at step 0."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "broken.simulation.json", {"run_input": "production/p.tpr"})

        with app.app_context():
            sim = Simulation.get(exp_id, "broken.simulation.json")
            assert sim.step == 0
            assert sim.status == "setup"

    def test_ladder_is_scoped_per_manifest(self, app: Flask, tmp_path: Path) -> None:
        """A finished job only moves its own simulation to the analyze step."""
        exp_id = _seed_experiment(app)
        _write_two_sims(tmp_path / exp_id)
        _add_gmx_job(
            app,
            exp_id,
            "protein.simulation.json",
            _last_known_status=JobStatus.FINISHED,
            _start_timestamp=1_700_000_100,
        )

        with app.app_context():
            protein = Simulation.get(exp_id, "protein.simulation.json")
            ligand = Simulation.get(exp_id, "ligand.simulation.json")
            assert protein.step == 4
            assert protein.status == "analyzing"
            assert ligand.step == 1
            assert ligand.status == "setup complete"

    def test_tuner_trials_give_step_two(self, app: Flask, tmp_path: Path) -> None:
        """A tuner trial with performance lifts only its own simulation to step 2 (no live API call)."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        with app.app_context():
            job = TunerJob(
                id=str(uuid.uuid4()),
                experiment_id=exp_id,
                simulation_path="protein.simulation.json",
                is_stopped=True,
                _preserved_trials=[{"performance": 12.3}],
                nsteps=25000,
            )
            db.session.add(job)
            db.session.commit()

            sim = Simulation.get(exp_id, "protein.simulation.json")
            assert sim.step == 2
            assert sim.status == "tuning"


class TestExperimentDelegation:
    """Experiment step inherits the latest simulation's step; publish state overrides."""

    def setup_method(self) -> None:
        """Clear the step status cache before each test."""
        from cache import step_status_cache

        step_status_cache.clear()

    def teardown_method(self) -> None:
        """Clear the step status cache after each test."""
        from cache import step_status_cache

        step_status_cache.clear()

    def test_no_manifests_is_setup(self, app: Flask) -> None:
        """An experiment without manifests sits at step 0."""
        exp_id = _seed_experiment(app)
        with app.app_context():
            experiment = db.session.get(Experiment, exp_id)
            assert experiment is not None
            assert experiment.step == 0
            assert experiment.status == "setup"

    def test_experiment_inherits_latest_simulation(self, app: Flask, tmp_path: Path) -> None:
        """Activity on the older simulation does not lift the experiment — the newer simulation leads."""
        exp_id = _seed_experiment(app)
        _write_two_sims(tmp_path / exp_id)
        from datetime import datetime

        _add_gmx_job(
            app,
            exp_id,
            "protein.simulation.json",
            _last_known_status=JobStatus.FINISHED,
            _start_timestamp=1_700_000_100,
            created_at=datetime.fromtimestamp(1_700_000_000),
        )

        with app.app_context():
            experiment = db.session.get(Experiment, exp_id)
            assert experiment is not None
            assert experiment.step == 1
            assert experiment.status == "setup complete"

    def test_just_started_job_makes_its_sim_latest(self, app: Flask, tmp_path: Path) -> None:
        """A freshly submitted job has no start/finish timestamps yet — its creation time must count."""
        exp_id = _seed_experiment(app)
        _write_two_sims(tmp_path / exp_id)  # ligand manifest is newer than protein's
        from datetime import datetime

        _add_gmx_job(app, exp_id, "protein.simulation.json", created_at=datetime.fromtimestamp(1_700_200_000))

        with app.app_context():
            experiment = db.session.get(Experiment, exp_id)
            assert experiment is not None
            protein = Simulation.get(exp_id, "protein.simulation.json")
            assert protein.last_activity >= 1_700_200_000
            # job row without timestamps still lifts its simulation (created_at) to latest — step 2
            assert experiment.step == 2
            assert experiment.status == "simulating"

    def test_analysis_job_makes_its_sim_latest(self, app: Flask, tmp_path: Path) -> None:
        """An analysis job's creation time lifts its own simulation's last_activity."""
        exp_id = _seed_experiment(app)
        _write_two_sims(tmp_path / exp_id)  # ligand manifest is newer than protein's
        from datetime import datetime

        from enums import AnalysisType
        from models import AnalysisJob

        with app.app_context():
            job = AnalysisJob(
                id=str(uuid.uuid4()),
                experiment_id=exp_id,
                simulation_path="protein.simulation.json",
                analysis_name=AnalysisType.RMSDS,
                structure_file="structure.pdb",
                trajectory_file="production/protein.xtc",
                created_at=datetime.fromtimestamp(1_700_200_000),
            )
            db.session.add(job)
            db.session.commit()

            experiment = db.session.get(Experiment, exp_id)
            assert experiment is not None
            latest = experiment._latest_simulation()
            assert latest is not None
            assert latest.name == "protein"

    def test_publish_state_overrides(self, app: Flask, tmp_path: Path) -> None:
        """Published/publishing (step 5) beats the latest simulation's step."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        from cache import step_status_cache

        with app.app_context():
            experiment = db.session.get(Experiment, exp_id)
            assert experiment is not None

            experiment.mdrepo_published = True
            assert experiment.step == 5
            assert experiment.status == "published"

            # the ladder is TTL-cached per instance; clear to observe the state change
            step_status_cache.clear()
            experiment.mdrepo_published = False
            assert experiment.step == 5
            assert experiment.status == "publishing"
