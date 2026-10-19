"""Unit tests for the Simulation class."""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from core.enums import Engine, JobStatus
from core.errors import ApiError, BadRequest
from modules.jobs.amber.schemas import AmberJob as AmberJobSchema
from modules.jobs.gmx.models import GromacsJob
from modules.jobs.gmx.schemas import GromacsJob as GromacsJobSchema
from modules.jobs.tuner.models import TunerJob
from modules.models import Experiment, Notebook
from modules.simulations.manifest import Simulation
from modules.simulations.manifest_schema import schema_url
from sqlalchemy.ext.asyncio import AsyncSession

GMX_SCHEMA_URL = schema_url(Engine.GMX)

GMX_FILES = {
    "run_input": "production/protein.tpr",
    "reference_structure": "analysis/protein-reference.gro",
    "trajectory": "production/protein.xtc",
}


async def _seed_experiment(db_session: AsyncSession, exp_id: str = "simts") -> str:
    """
    Seed a minimal experiment into the DB.

    Returns:
        The experiment ID.
    """
    db_session.add(Experiment(id=exp_id, name="Sim Test", notebooks_repo="https://github.com/t/r.git"))
    db_session.add(Notebook(experiment_id=exp_id))
    await db_session.commit()
    return exp_id


async def _experiment(db_session: AsyncSession, exp_id: str) -> Experiment:
    """Load the experiment with its jobs as a request would, with remote job status refreshed."""
    await db_session.commit()
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, exp_id)
    assert experiment is not None
    await experiment.refresh_jobs()
    return experiment


async def _sim(db_session: AsyncSession, exp_id: str, simulation_path: str) -> Simulation:
    return Simulation.get(exp_id, simulation_path, await _experiment(db_session, exp_id))


async def _sims(db_session: AsyncSession, exp_id: str) -> list[Simulation]:
    return Simulation.list(exp_id, await _experiment(db_session, exp_id))


async def _job(db_session: AsyncSession) -> GromacsJob:
    """Load the experiment's single GROMACS job with its status refreshed."""
    await db_session.commit()
    db_session.expunge_all()
    job = (await db_session.execute(GromacsJob.query())).scalars().one()
    await job.refresh_status()
    return job


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

    async def test_finds_simulation_anywhere(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Simulations are discovered in nested directories."""
        exp_id = await _seed_experiment(db_session)
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

        sims = await _sims(db_session, exp_id)
        paths = [s.simulation_path for s in sims]
        assert "protein.simulation.json" in paths
        assert "equilibration/nvt.simulation.json" in paths

    async def test_sorted_by_path(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Discovery results are sorted by path."""
        exp_id = await _seed_experiment(db_session)
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

        sims = await _sims(db_session, exp_id)
        assert sims[0].simulation_path == "a.simulation.json"
        assert sims[1].simulation_path == "z.simulation.json"


class TestValidation:
    """Missing $schema target makes simulation invalid."""

    async def test_missing_schema_makes_invalid(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Missing $schema target invalidates the simulation."""
        exp_id = await _seed_experiment(db_session)
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

        sim = await _sim(db_session, exp_id, sim_path)
        assert not sim.valid
        assert any("schema" in e.lower() or "missing" in e.lower() for e in sim.errors)

    async def test_valid_simulation(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A complete simulation with existing files is valid."""
        exp_id = await _seed_experiment(db_session)
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

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.valid
        assert sim.missing_files == []

    async def test_require_files_can_limit_required_roles(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Action validation only requires the roles needed by that action."""
        exp_id = await _seed_experiment(db_session)
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

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.missing_files == ["reference_structure", "trajectory"]

        sim.require_files(["run_input"])

        with pytest.raises(BadRequest, match="Missing files for: 'Reference structure', 'Trajectory'"):
            sim.require_files()


class TestPathResolution:
    """Role paths resolve relative to the manifest directory, with an experiment-relative fallback."""

    async def test_nested_manifest_paths_are_manifest_relative(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Notebook-written manifests live beside their outputs and reference them cwd-relative."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "gromacs/dnarna/hammerhead.simulation.json",
            {
                "run_input": "production/hammerhead.tpr",
                "reference_structure": "analysis/hammerhead-reference.gro",
                "trajectory": "production/hammerhead.xtc",
            },
            name="hammerhead",
        )
        tpr = exp_dir / "gromacs/dnarna/production/hammerhead.tpr"
        tpr.parent.mkdir(parents=True, exist_ok=True)
        tpr.write_bytes(b"\x00")
        reference = exp_dir / "gromacs/dnarna/analysis/hammerhead-reference.gro"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_text("gro")

        sim = await _sim(db_session, exp_id, "gromacs/dnarna/hammerhead.simulation.json")
        assert sim.resolved_files["run_input"] == "gromacs/dnarna/production/hammerhead.tpr"
        assert sim.resolved_files["reference_structure"] == "gromacs/dnarna/analysis/hammerhead-reference.gro"
        # Not-yet-created outputs (trajectory is produced by the run) resolve manifest-relative too.
        assert sim.resolved_files["trajectory"] == "gromacs/dnarna/production/hammerhead.xtc"
        assert sim.valid
        assert sim.missing_files == ["trajectory"]
        assert sim.resolve_role("run_input") == tpr

    async def test_experiment_relative_paths_resolve_via_fallback(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """The fallback keeps mixed conventions (e.g. hand-fixed manifests) resolving."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "equilibration/nvt.simulation.json",
            {
                "run_input": "equilibration/nvt.tpr",
                "reference_structure": "equilibration/nvt-reference.gro",
                "trajectory": "equilibration/nvt.xtc",
            },
            name="nvt",
        )
        (exp_dir / "equilibration/nvt.tpr").write_bytes(b"\x00")
        (exp_dir / "equilibration/nvt-reference.gro").write_text("gro")
        (exp_dir / "equilibration/nvt.xtc").write_bytes(b"\x00")

        sim = await _sim(db_session, exp_id, "equilibration/nvt.simulation.json")
        assert sim.resolved_files["run_input"] == "equilibration/nvt.tpr"
        assert sim.valid
        assert sim.missing_files == []

    async def test_missing_everywhere_reports_manifest_relative(self, db_session: AsyncSession, tmp_path: Path) -> None:
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(
            exp_dir,
            "gromacs/dnarna/hammerhead.simulation.json",
            {
                "run_input": "production/hammerhead.tpr",
                "reference_structure": "analysis/hammerhead-reference.gro",
                "trajectory": "production/hammerhead.xtc",
            },
            name="hammerhead",
        )

        sim = await _sim(db_session, exp_id, "gromacs/dnarna/hammerhead.simulation.json")
        assert sim.resolved_files["run_input"] == "gromacs/dnarna/production/hammerhead.tpr"
        assert sim.missing_files == ["run_input", "reference_structure", "trajectory"]

    async def test_escaping_path_is_rejected(self, db_session: AsyncSession, tmp_path: Path) -> None:
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "nested/hammerhead.simulation.json",
            {
                "run_input": "/etc/passwd",
                "reference_structure": "analysis/hammerhead-reference.gro",
                "trajectory": "production/hammerhead.xtc",
            },
            name="hammerhead",
        )

        sim = await _sim(db_session, exp_id, sim_path)
        assert sim.resolved_files["run_input"] == "/etc/passwd"
        with pytest.raises(BadRequest, match="outside the experiment folder"):
            sim.resolve_role("run_input")


class TestWriteRebase:
    """write()/update() store submitted experiment-relative values manifest-relative."""

    async def test_create_rebases_prefixed_values(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Form-submitted experiment-relative values are stripped of the manifest-dir prefix."""
        exp_id = await _seed_experiment(db_session)
        (tmp_path / exp_id).mkdir(parents=True, exist_ok=True)

        sim = Simulation.write(
            await _experiment(db_session, exp_id),
            {
                "name": "hammerhead",
                "simulation_path": "gromacs/dnarna/hammerhead.simulation.json",
                "files": {
                    "run_input": "gromacs/dnarna/production/hammerhead.tpr",
                    "reference_structure": "gromacs/dnarna/analysis/hammerhead-reference.gro",
                    "trajectory": "gromacs/dnarna/production/hammerhead.xtc",
                },
                "extra_args": "",
            },
        )

        assert sim.files == {
            "run_input": "production/hammerhead.tpr",
            "reference_structure": "analysis/hammerhead-reference.gro",
            "trajectory": "production/hammerhead.xtc",
        }
        on_disk = json.loads((tmp_path / exp_id / sim.simulation_path).read_text())
        assert on_disk["files"]["run_input"] == "production/hammerhead.tpr"

    async def test_create_keeps_manifest_relative_values(self, db_session: AsyncSession, tmp_path: Path) -> None:
        exp_id = await _seed_experiment(db_session)
        (tmp_path / exp_id).mkdir(parents=True, exist_ok=True)

        sim = Simulation.write(
            await _experiment(db_session, exp_id),
            {
                "name": "hammerhead",
                "simulation_path": "gromacs/dnarna/hammerhead.simulation.json",
                "files": {
                    "run_input": "production/hammerhead.tpr",
                    "reference_structure": "analysis/hammerhead-reference.gro",
                    "trajectory": "shared/hammerhead.xtc",  # outside the manifest dir: no strip
                },
                "extra_args": "",
            },
        )

        assert sim.files["run_input"] == "production/hammerhead.tpr"
        assert sim.files["trajectory"] == "shared/hammerhead.xtc"

    async def test_create_at_root_keeps_values(self, db_session: AsyncSession, tmp_path: Path) -> None:
        exp_id = await _seed_experiment(db_session)
        (tmp_path / exp_id).mkdir(parents=True, exist_ok=True)

        sim = Simulation.write(
            await _experiment(db_session, exp_id),
            {
                "name": "protein",
                "simulation_path": "protein.simulation.json",
                "files": {
                    "run_input": "production/protein.tpr",
                    "reference_structure": "analysis/protein-reference.gro",
                    "trajectory": "production/protein.xtc",
                },
                "extra_args": "",
            },
        )

        assert sim.files["run_input"] == "production/protein.tpr"

    async def test_update_rebases_prefixed_values(self, db_session: AsyncSession, tmp_path: Path) -> None:
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "gromacs/dnarna/hammerhead.simulation.json",
            {
                "run_input": "production/hammerhead.tpr",
                "reference_structure": "analysis/hammerhead-reference.gro",
                "trajectory": "production/hammerhead.xtc",
            },
            name="hammerhead",
        )

        sim = Simulation.update(
            await _experiment(db_session, exp_id),
            sim_path,
            {
                "name": "hammerhead",
                "files": {
                    "run_input": "gromacs/dnarna/production/hammerhead.tpr",
                    "reference_structure": "gromacs/dnarna/analysis/hammerhead-reference.gro",
                    "trajectory": "gromacs/dnarna/production/hammerhead.xtc",
                },
                "extra_args": "",
            },
        )

        assert sim.files["run_input"] == "production/hammerhead.tpr"
        on_disk = json.loads((tmp_path / exp_id / sim_path).read_text())
        assert on_disk["files"]["trajectory"] == "production/hammerhead.xtc"

    async def test_resolve_role_matches_resolved_files_when_both_candidates_exist(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """With both candidates on disk, manifest-relative wins — identically for every consumer."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "gromacs/dnarna/hammerhead.simulation.json",
            {
                "run_input": "production/hammerhead.tpr",
                "reference_structure": "analysis/hammerhead-reference.gro",
                "trajectory": "production/hammerhead.xtc",
            },
            name="hammerhead",
        )
        (exp_dir / "gromacs/dnarna/production").mkdir(parents=True, exist_ok=True)
        (exp_dir / "gromacs/dnarna/production/hammerhead.tpr").write_bytes(b"\x00")
        (exp_dir / "production").mkdir(parents=True, exist_ok=True)
        (exp_dir / "production/hammerhead.tpr").write_bytes(b"\x00")

        sim = await _sim(db_session, exp_id, sim_path)
        assert sim.resolved_files["run_input"] == "gromacs/dnarna/production/hammerhead.tpr"
        assert sim.resolve_role("run_input") == exp_dir / "gromacs/dnarna/production/hammerhead.tpr"


class TestLocking:
    """Lock inference from file permissions and job references."""

    async def test_readonly_file_without_jobs_is_locked(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A read-only file with no jobs is locked by file permissions."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {"run_input": "p.tpr", "reference_structure": "p-reference.gro", "trajectory": "p.xtc"},
        )

        sim = await _sim(db_session, exp_id, sim_path)
        assert not sim.locked
        sim.mark_readonly()
        assert sim.locked

    async def test_writable_unlocked_file_not_locked(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A writable file with no jobs is not locked."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        sim_path = _write_sim_file(
            exp_dir,
            "protein.simulation.json",
            {"run_input": "p.tpr", "reference_structure": "p-reference.gro", "trajectory": "p.xtc"},
        )

        sim = await _sim(db_session, exp_id, sim_path)
        assert not sim.locked


class TestWriteSimulation:
    """Create simulation JSON via Simulation.write."""

    async def test_create_simulation(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Simulation.write creates a valid manifest at the default path."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        sim = Simulation.write(
            await _experiment(db_session, exp_id),
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

    async def test_create_rejects_existing_simulation_path(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Creating a simulation must not silently overwrite an existing manifest."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        Simulation.write(
            await _experiment(db_session, exp_id),
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
                await _experiment(db_session, exp_id),
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

    async def test_create_rejects_invalid_content(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Invalid content is rejected before writing."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(BadRequest, match="Missing required file role: 'Reference structure'"):
            Simulation.write(
                await _experiment(db_session, exp_id),
                {
                    "name": "protein",
                    "files": {"run_input": "production/protein.tpr"},
                    "extra_args": "",
                },
            )

    async def test_validation_message_is_human_readable(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Regexes and jsonschema wording must not leak into user-facing errors."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(BadRequest) as exc_info:
            Simulation.write(
                await _experiment(db_session, exp_id),
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


async def _add_gmx_job(db_session: AsyncSession, exp_id: str, simulation_path: str, **kwargs: object) -> None:
    """Persist a GromacsJob for the given simulation."""
    from core.enums import DeviceType

    db_session.add(
        GromacsJob(
            id=str(uuid.uuid4()),
            experiment_id=exp_id,
            simulation_path=simulation_path,
            np=1,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.CPU,
            **kwargs,
        )
    )
    await db_session.commit()


class TestUniqueName:
    """Simulation names must be unique per experiment — they are the wizard tab identity."""

    async def test_create_rejects_duplicate_name(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A second manifest with an existing name is rejected with a conflict."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        Simulation.write(
            await _experiment(db_session, exp_id), {"name": "protein", "files": GMX_FILES, "extra_args": ""}
        )

        with pytest.raises(ApiError, match="already exists") as exc_info:
            Simulation.write(
                await _experiment(db_session, exp_id),
                {
                    "name": "protein",
                    "simulation_path": "other.simulation.json",
                    "files": GMX_FILES,
                    "extra_args": "",
                },
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.problem_type == "urn:mddash:duplicate-simulation-name"

    async def test_update_rejects_duplicate_name(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Renaming a manifest to another manifest's name is rejected."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")
        _write_sim_file(exp_dir, "ligand.simulation.json", GMX_FILES, name="ligand")

        with pytest.raises(ApiError, match="already exists"):
            Simulation.update(
                await _experiment(db_session, exp_id), "ligand.simulation.json", {"name": "protein", "files": GMX_FILES}
            )

    async def test_update_allows_keeping_own_name(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Updating a manifest without changing its name is fine."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")

        sim = Simulation.update(
            await _experiment(db_session, exp_id), "protein.simulation.json", {"name": "protein", "files": GMX_FILES}
        )
        assert sim.name == "protein"

    async def test_reserved_new_name_rejected(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """`_new` is reserved for the wizard's create tab."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ApiError, match="reserved") as exc_info:
            Simulation.write(
                await _experiment(db_session, exp_id), {"name": "_new", "files": GMX_FILES, "extra_args": ""}
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.problem_type == "urn:mddash:duplicate-simulation-name"

        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")
        with pytest.raises(ApiError, match="reserved"):
            Simulation.update(
                await _experiment(db_session, exp_id), "protein.simulation.json", {"name": "_new", "files": GMX_FILES}
            )


def _write_two_sims(exp_dir: Path) -> None:
    """Write 'protein' and 'ligand' manifests with protein's mtime older."""
    exp_dir.mkdir(parents=True, exist_ok=True)
    _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES, name="protein")
    _write_sim_file(exp_dir, "ligand.simulation.json", GMX_FILES, name="ligand")
    _set_mtime(exp_dir / "protein.simulation.json", 1_700_000_000)
    _set_mtime(exp_dir / "ligand.simulation.json", 1_700_100_000)


class TestStepStatus:
    """Per-simulation ladder: each manifest infers its own step from its own jobs."""

    async def test_valid_manifest_without_jobs_is_setup_complete(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """A valid manifest with no jobs sits at step 1."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.step == 1
        assert sim.status == "setup complete"
        assert sim.to_dict()["step"] == 1

    async def test_invalid_manifest_is_setup(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """An invalid manifest sits at step 0."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "broken.simulation.json", {"run_input": "production/p.tpr"})

        sim = await _sim(db_session, exp_id, "broken.simulation.json")
        assert sim.step == 0
        assert sim.status == "setup"

    async def test_ladder_is_scoped_per_manifest(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A finished job only moves its own simulation to the analyze step."""
        exp_id = await _seed_experiment(db_session)
        _write_two_sims(tmp_path / exp_id)
        await _add_gmx_job(
            db_session,
            exp_id,
            "protein.simulation.json",
            _last_known_status=JobStatus.FINISHED,
            _start_timestamp=1_700_000_100,
        )

        protein = await _sim(db_session, exp_id, "protein.simulation.json")
        ligand = await _sim(db_session, exp_id, "ligand.simulation.json")
        assert protein.step == 3
        assert protein.status == "analyzing"
        assert ligand.step == 1
        assert ligand.status == "setup complete"

    async def test_pending_sim_job_stays_at_step_two(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A submitted job counts toward the ladder only once it is actually running."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json")

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.step == 2
        assert sim.status == "simulating"

    async def test_running_sim_job_stays_at_step_two_until_progress_is_known(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """A just-started run has no engine log yet: Analyze waits for parsed progress (implies the trajectory exists)."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json", _last_known_status=JobStatus.RUNNING)

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.step == 2
        assert sim.status == "simulating"

    async def test_running_sim_job_activates_analyze_once_progress_is_known(
        self, db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A running job with parsed nsteps_done counts the run as done: Analyze activates (partial trajectories analyzable mid-run)."""
        monkeypatch.setattr("modules.jobs.gmx.models.DATA_DIR", tmp_path)
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json", _last_known_status=JobStatus.RUNNING)

        production = exp_dir / "production"
        production.mkdir()
        (production / "protein.log").write_text(
            "header\n"
            "nsteps = 50000\n"
            "Started mdrun on rank 0 Thu Aug 21 09:00:00 2026\n"
            "           40000     800.00000    Thu Aug 21 09:10:00 2026\n"
        )

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.step == 3
        assert sim.status == "simulating"

    async def test_tuner_trials_give_step_two(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A tuner trial with performance lifts only its own simulation to step 2 (no live API call)."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        job = TunerJob(
            id=str(uuid.uuid4()),
            experiment_id=exp_id,
            simulation_path="protein.simulation.json",
            is_stopped=True,
            _preserved_trials=[{"performance": 12.3}],
            nsteps=25000,
        )
        db_session.add(job)
        await db_session.commit()

        sim = await _sim(db_session, exp_id, "protein.simulation.json")
        assert sim.step == 2
        assert sim.status == "tuning"

    async def test_pending_and_running_jobs_are_live(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Non-terminal jobs keep the simulation live; the dict carries the flag."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        _write_sim_file(exp_dir, "ligand.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json")
        await _add_gmx_job(db_session, exp_id, "ligand.simulation.json", _last_known_status=JobStatus.RUNNING)

        assert (await _sim(db_session, exp_id, "protein.simulation.json")).live is True
        assert (await _sim(db_session, exp_id, "ligand.simulation.json")).live is True
        assert (await _sim(db_session, exp_id, "protein.simulation.json")).to_dict()["live"] is True

    async def test_terminal_jobs_are_not_live(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Finished/failed jobs and stopped tuner jobs leave the simulation settled."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json", _last_known_status=JobStatus.FINISHED)

        tuner = TunerJob(
            id=str(uuid.uuid4()),
            experiment_id=exp_id,
            simulation_path="protein.simulation.json",
            is_stopped=True,  # stopped jobs report UNKNOWN status but are terminal
            nsteps=25000,
        )
        db_session.add(tuner)
        await db_session.commit()

        assert (await _sim(db_session, exp_id, "protein.simulation.json")).live is False

    async def test_no_jobs_is_not_live(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A bare manifest has nothing in flight."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        assert (await _sim(db_session, exp_id, "protein.simulation.json")).live is False


class TestLogLines:
    """SimulationJob.log_lines rides the job payload so the UI shows log sizes without fetching them."""

    async def test_none_until_logs_exist_and_counts_afterwards(
        self, db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing streams report None; written streams report their line count."""
        monkeypatch.setattr("modules.jobs.gmx.models.DATA_DIR", tmp_path)
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json")

        job = await _job(db_session)
        assert job.log_lines == {"gmx": None, "stdout": None, "stderr": None}

        production = exp_dir / "production"
        production.mkdir()
        (production / "protein.log").write_text("a\nb\nc\n")
        (production / f"mdrun-{job.id}.out").write_text("x\n")

        from core.cache import simulation_log_lines_cache

        simulation_log_lines_cache.clear()
        assert job.log_lines == {"gmx": 3, "stdout": 1, "stderr": None}

    async def test_finished_count_reflects_immediately_without_stale_caches(
        self, db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Regression: a dump right after the finish flip must not serve a stale step count.

        The derived fields used to sit behind TTL caches (100ms-1s) evaluated
        independently of status, so one payload could say FINISHED with a
        step count from before the flip.
        """
        monkeypatch.setattr("modules.jobs.gmx.models.DATA_DIR", tmp_path)
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json", _last_known_status=JobStatus.RUNNING)

        production = exp_dir / "production"
        production.mkdir()
        log = production / "protein.log"
        log.write_text(
            "header\n"
            "nsteps = 50000\n"
            "Started mdrun on rank 0 Thu Aug 21 09:00:00 2026\n"
            "           40000     800.00000    Thu Aug 21 09:10:00 2026\n"
        )

        job = await _job(db_session)
        assert GromacsJobSchema.model_validate(job).model_dump(mode="json")["nsteps_done"] == 40000

        # The finish flip lands between two polls (status swap + performance persist).
        log.write_text(
            "header\n"
            "nsteps = 50000\n"
            "Started mdrun on rank 0 Thu Aug 21 09:00:00 2026\n"
            "           40000     800.00000    Thu Aug 21 09:10:00 2026\n"
            "           50000    1000.00000    Thu Aug 21 09:20:00 2026\n"
            "Finished mdrun\n"
        )
        job._performance = 62.5
        await db_session.commit()

        fresh = await _job(db_session)
        dumped = GromacsJobSchema.model_validate(fresh).model_dump(mode="json")
        assert dumped["nsteps_done"] == 50000
        assert dumped["performance"] == 62.5

    async def test_pme_and_nb_serialize_by_contract_value(
        self, db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        OpenAPI declares pme/nb as lowercase [cpu, gpu] — the payload must match.

        The UI compares these against tuner-trial configs (lowercase) when
        rendering "Configuration used"; name-cased values silently break that.
        """
        monkeypatch.setattr("modules.jobs.gmx.models.DATA_DIR", tmp_path)
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json")

        job = await _job(db_session)
        dumped = GromacsJobSchema.model_validate(job).model_dump(mode="json")
        assert dumped["pme"] == "cpu"
        assert dumped["nb"] == "cpu"

    async def test_binary_and_ewald_serialize_by_contract_value(self, db_session: AsyncSession) -> None:
        """
        Same contract as gmx pme/nb: OpenAPI declares values (pmemd.cuda).

        Re-run re-POSTs the dumped fields and trial matching compares against
        values, so name-cased payloads (PMEMD_CUDA) break both flows.
        """
        from core.enums import AmberBinary, EwaldPreset
        from modules.jobs.amber.models import AmberJob

        job = AmberJob(
            id=str(uuid.uuid4()),
            experiment_id="exp",
            simulation_path="protein.simulation.json",
            np=1,
            ntomp=1,
            binary=AmberBinary.PMEMD_CUDA,
            ewald=EwaldPreset.DEFAULT,
            engine=Engine.AMBER,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            _last_known_status=JobStatus.FINISHED,
        )
        dumped = AmberJobSchema.model_validate(job).model_dump(mode="json")
        assert dumped["binary"] == "pmemd.cuda"
        assert dumped["ewald"] == "default"

    async def test_serialized_with_the_job_payload(
        self, db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The auto schema includes log_lines without extra schema code."""
        monkeypatch.setattr("modules.jobs.gmx.models.DATA_DIR", tmp_path)
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json")

        job = await _job(db_session)
        dumped = GromacsJobSchema.model_validate(job).model_dump(mode="json")
        assert dumped["log_lines"] == {"gmx": None, "stdout": None, "stderr": None}


class TestExperimentDelegation:
    """Experiment step inherits the latest simulation's step; publish state overrides."""

    async def test_no_manifests_is_setup(self, db_session: AsyncSession) -> None:
        """An experiment without manifests sits at step 0."""
        exp_id = await _seed_experiment(db_session)
        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        assert experiment.step == 0
        assert experiment.status == "setup"

    async def test_experiment_inherits_latest_simulation(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Activity on the older simulation does not lift the experiment — the newer simulation leads."""
        exp_id = await _seed_experiment(db_session)
        _write_two_sims(tmp_path / exp_id)
        from datetime import datetime

        await _add_gmx_job(
            db_session,
            exp_id,
            "protein.simulation.json",
            _last_known_status=JobStatus.FINISHED,
            _start_timestamp=1_700_000_100,
            created_at=datetime.fromtimestamp(1_700_000_000),
        )

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        assert experiment.step == 1
        assert experiment.status == "setup complete"

    async def test_just_started_job_makes_its_sim_latest(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A freshly submitted job has no start/finish timestamps yet — its creation time must count."""
        exp_id = await _seed_experiment(db_session)
        _write_two_sims(tmp_path / exp_id)  # ligand manifest is newer than protein's
        from datetime import datetime

        await _add_gmx_job(
            db_session, exp_id, "protein.simulation.json", created_at=datetime.fromtimestamp(1_700_200_000)
        )

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        protein = await _sim(db_session, exp_id, "protein.simulation.json")
        assert protein.last_activity >= 1_700_200_000
        # job row without timestamps still lifts its simulation (created_at) to latest — step 2
        assert experiment.step == 2
        assert experiment.status == "simulating"

    async def test_analysis_job_makes_its_sim_latest(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """An analysis job's creation time lifts its own simulation's last_activity."""
        exp_id = await _seed_experiment(db_session)
        _write_two_sims(tmp_path / exp_id)  # ligand manifest is newer than protein's
        from datetime import datetime

        from core.enums import AnalysisType
        from modules.models import AnalysisJob

        job = AnalysisJob(
            id=str(uuid.uuid4()),
            experiment_id=exp_id,
            simulation_path="protein.simulation.json",
            analysis_name=AnalysisType.RMSDS,
            structure_file="structure.pdb",
            trajectory_file="production/protein.xtc",
            created_at=datetime.fromtimestamp(1_700_200_000),
        )
        db_session.add(job)
        await db_session.commit()

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        latest = experiment._latest_simulation()
        assert latest is not None
        assert latest.name == "protein"

    async def test_publish_state_overrides(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Published/publishing (step 4) beats the latest simulation's step."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None

        experiment.mdrepo_published = True
        assert experiment.step == 4
        assert experiment.status == "published"

        # the ladder is memoized per instance (one request); reset to observe the state change
        experiment._memo_step = None
        experiment.mdrepo_published = False
        assert experiment.step == 4
        assert experiment.status == "publishing"


class TestCanPublish:
    """can_publish is the experiment-level Publish unlock: a draft exists, or any run finished."""

    async def test_false_without_draft_or_finished_run(self, db_session: AsyncSession) -> None:
        exp_id = await _seed_experiment(db_session)
        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        assert experiment.can_publish is False

    async def test_running_run_does_not_unlock(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A running run is still in the Run phase — Analyze (and Publish) wait for the finish."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json", _last_known_status=JobStatus.RUNNING)

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        assert experiment.can_publish is False

    async def test_stopped_run_unlocks_publish(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Stopped ⇔ finished: partial results are publishable (mirrors the step ladder's analyzing handling)."""
        exp_id = await _seed_experiment(db_session)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_sim_file(exp_dir, "protein.simulation.json", GMX_FILES)
        await _add_gmx_job(db_session, exp_id, "protein.simulation.json", _last_known_status=JobStatus.STOPPED)

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        assert experiment.can_publish is True

    async def test_finished_run_unlocks_even_when_not_latest(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A finished non-latest run leaves the ladder at the latest sim but unlocks Publish."""
        exp_id = await _seed_experiment(db_session)
        _write_two_sims(tmp_path / exp_id)
        from datetime import datetime

        await _add_gmx_job(
            db_session,
            exp_id,
            "protein.simulation.json",
            _last_known_status=JobStatus.FINISHED,
            _start_timestamp=1_700_000_100,
            created_at=datetime.fromtimestamp(1_700_000_000),
        )

        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        assert experiment.step == 1  # ligand is newer — the ladder follows it
        assert experiment.can_publish is True

    async def test_draft_unlocks_without_any_run(self, db_session: AsyncSession) -> None:
        exp_id = await _seed_experiment(db_session)
        experiment = await _experiment(db_session, exp_id)
        assert experiment is not None
        experiment.mdrepo_id = "rec123"
        assert experiment.can_publish is True
