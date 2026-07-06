"""Unit tests for the Simulation class."""

import json
import os
from pathlib import Path

import pytest
from extensions import db
from flask import Flask
from models import Experiment, Notebook
from models.simulation import Simulation
from werkzeug.exceptions import BadRequest

GMX_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "MDDash GROMACS simulation manifest",
    "type": "object",
    "required": ["name", "engine", "files", "extra_args"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string"},
        "name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"},
        "engine": {"const": "GMX"},
        "files": {
            "type": "object",
            "required": ["topology", "structure", "trajectory"],
            "additionalProperties": False,
            "properties": {
                "topology": {"type": "string"},
                "structure": {"type": "string"},
                "trajectory": {"type": "string"},
            },
        },
        "extra_args": {"type": "string"},
    },
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


def _write_schema(exp_dir: Path) -> None:
    (exp_dir / "gromacs.schema.json").write_text(json.dumps(GMX_SCHEMA))


def _write_sim_file(exp_dir: Path, simulation_path: str, files: dict, name: str = "protein") -> str:
    """
    Write a GMX simulation manifest.

    Returns:
        The simulation_path.
    """
    sim_file = exp_dir / simulation_path
    sim_file.parent.mkdir(parents=True, exist_ok=True)
    sim_dir = sim_file.parent
    content = {
        "$schema": os.path.relpath(exp_dir / "gromacs.schema.json", sim_dir),
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
        _write_schema(exp_dir)
        _write_sim_file(
            exp_dir,
            "production/protein.simulation.json",
            {"topology": "protein.tpr", "structure": "protein.gro", "trajectory": "protein.xtc"},
        )
        _write_sim_file(
            exp_dir,
            "equilibration/nvt.simulation.json",
            {"topology": "nvt.tpr", "structure": "nvt.gro", "trajectory": "nvt.xtc"},
        )

        with app.app_context():
            sims = Simulation.list(exp_id)
            paths = [s.simulation_path for s in sims]
            assert "production/protein.simulation.json" in paths
            assert "equilibration/nvt.simulation.json" in paths

    def test_sorted_by_path(self, app: Flask, tmp_path: Path) -> None:
        """Discovery results are sorted by path."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_schema(exp_dir)
        _write_sim_file(
            exp_dir, "z.simulation.json", {"topology": "z.tpr", "structure": "z.gro", "trajectory": "z.xtc"}
        )
        _write_sim_file(
            exp_dir, "a.simulation.json", {"topology": "a.tpr", "structure": "a.gro", "trajectory": "a.xtc"}
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
        sim_path = "production/protein.simulation.json"
        sim_file = exp_dir / sim_path
        sim_file.parent.mkdir(parents=True, exist_ok=True)
        content = {
            "$schema": "../gromacs.schema.json",
            "name": "protein",
            "engine": "GMX",
            "files": {"topology": "protein.tpr", "structure": "protein.gro", "trajectory": "protein.xtc"},
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
        _write_schema(exp_dir)
        _write_sim_file(
            exp_dir,
            "production/protein.simulation.json",
            {"topology": "protein.tpr", "structure": "protein.gro", "trajectory": "protein.xtc"},
        )
        (exp_dir / "production" / "protein.tpr").write_bytes(b"\x00")
        (exp_dir / "production" / "protein.gro").write_text("gro")
        (exp_dir / "production" / "protein.xtc").write_bytes(b"\x00")

        with app.app_context():
            sim = Simulation.get(exp_id, "production/protein.simulation.json")
            assert sim.valid
            assert sim.missing_files == []


class TestLocking:
    """Lock inference from file permissions and job references."""

    def test_readonly_file_is_locked(self, app: Flask, tmp_path: Path) -> None:
        """A read-only file is treated as locked."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_schema(exp_dir)
        sim_path = _write_sim_file(
            exp_dir, "protein.simulation.json", {"topology": "p.tpr", "structure": "p.gro", "trajectory": "p.xtc"}
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
        _write_schema(exp_dir)
        sim_path = _write_sim_file(
            exp_dir, "protein.simulation.json", {"topology": "p.tpr", "structure": "p.gro", "trajectory": "p.xtc"}
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
        _write_schema(exp_dir)

        with app.app_context():
            sim = Simulation.write(
                exp_id,
                {
                    "name": "protein",
                    "files": {"topology": "protein.tpr", "structure": "protein.gro", "trajectory": "protein.xtc"},
                    "extra_args": "-v",
                },
            )
            assert sim.simulation_path == "production/protein.simulation.json"
            assert sim.name == "protein"
            assert sim.valid

    def test_create_rejects_existing_simulation_path(self, app: Flask, tmp_path: Path) -> None:
        """Creating a simulation must not silently overwrite an existing manifest."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_schema(exp_dir)

        with app.app_context():
            Simulation.write(
                exp_id,
                {
                    "name": "protein",
                    "files": {"topology": "protein.tpr", "structure": "protein.gro", "trajectory": "protein.xtc"},
                    "extra_args": "",
                },
            )

            with pytest.raises(BadRequest, match="already exists"):
                Simulation.write(
                    exp_id,
                    {
                        "name": "protein",
                        "files": {"topology": "other.tpr", "structure": "other.gro", "trajectory": "other.xtc"},
                        "extra_args": "",
                    },
                )

    def test_create_rejects_invalid_content(self, app: Flask, tmp_path: Path) -> None:
        """Invalid content is rejected before writing."""
        exp_id = _seed_experiment(app)
        exp_dir = tmp_path / exp_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        _write_schema(exp_dir)

        with app.app_context(), pytest.raises(BadRequest):
            Simulation.write(
                exp_id,
                {
                    "name": "protein",
                    "files": {"topology": "protein.tpr"},
                    "extra_args": "",
                },
            )
