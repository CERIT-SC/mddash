"""Builders shared by the test modules (fixtures live in conftest.py)."""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from core.enums import Engine
from modules.simulations.manifest_schema import schema_url

GMX_FILES = {
    "run_input": "production/protein.tpr",
    "reference_structure": "analysis/protein-reference.gro",
    "trajectory": "production/protein.xtc",
}

AMBER_FILES = {
    "topology": "prod.prmtop",
    "coordinates": "prod.inpcrd",
    "control": "prod.mdin",
    "reference_structure": "reference.pdb",
    "trajectory": "prod.nc",
}


def write_simulation(
    exp_dir: Path,
    simulation_path: str = "protein.simulation.json",
    files: dict | None = None,
    *,
    engine: Engine = Engine.GMX,
    name: str = "protein",
    extra_args: str = "",
    inputs: tuple[str, ...] = (),
) -> str:
    """Write a manifest (files default per engine) and a placeholder file for each role in `inputs`; returns its path."""
    files = files if files is not None else (GMX_FILES if engine is Engine.GMX else AMBER_FILES)
    manifest = exp_dir / simulation_path
    manifest.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "$schema": schema_url(engine),
        "name": name,
        "engine": engine.value,
        "files": files,
        "extra_args": extra_args,
    }
    manifest.write_text(json.dumps(content))
    for role in inputs:
        path = manifest.parent / files[role]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"demo {role}\n")
    return simulation_path


type SeedExperiment = Callable[..., Awaitable[tuple[str, Path]]]


def pod(phase: str = "Running", started: datetime | None = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)) -> MagicMock:
    """
    Plausible Kubernetes pod read.

    Default MagicMock attributes produce truthy deletion_timestamps and non-datetime start_times that break
    serialization.
    """
    result = MagicMock()
    result.metadata.deletion_timestamp = None
    result.status.phase = phase
    result.status.container_statuses = []
    result.status.start_time = started
    return result
