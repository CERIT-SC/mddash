"""Seeded experiment files and simulation manifests."""

import os
from datetime import datetime, timedelta

from core.config import DATA_DIR

from ..files import (
    ensure_amber_demo_files,
    ensure_demo_files,
    ensure_mdposit_demo_files,
    write_amber_simulation,
    write_gmx_simulation,
)
from ..state import E2E
from .experiments import (
    AMBER_DNA,
    AMBER_FOLDING,
    E2E_AMBER_TETRA,
    E2E_GMX_STUDIES,
    ENZYME,
    MDPOSIT_IMPORT,
    MEMBRANE,
    PUBLISHED,
)


def seed_files() -> None:
    """Write each experiment's input files (the archived experiment has none: its dir is gone)."""
    ensure_demo_files(MEMBRANE, ["gpcr_membrane.tpr", "structure.pdb", "trajectory.xtc"])
    # Enzyme study: includes subdirectory, long filename, and multiple runs
    ensure_demo_files(
        ENZYME,
        [
            "production/md.tpr",
            "npt_equilibration.tpr",
            "hiv_protease_apo_enzyme_wild_type_production_run_2024.tpr",
            "structure.pdb",
            "trajectory.xtc",
            "equilibration/nvt.tpr",
        ],
    )
    ensure_demo_files(PUBLISHED, ["lysozyme_hewl.tpr", "structure.pdb", "trajectory.xtc", "input.pdb"])
    ensure_amber_demo_files(
        AMBER_FOLDING,
        prmtop_name="villin.prmtop",
        inpcrd_name="villin.inpcrd",
        mdin_names=["production.mdin", "equilibration.mdin"],
    )
    ensure_amber_demo_files(
        AMBER_DNA, prmtop_name="dna.prmtop", inpcrd_name="dna.inpcrd", mdin_names=["simulation.mdin"]
    )
    # Mirrors the project file layout the fake MDPosit API exposes.
    ensure_mdposit_demo_files(MDPOSIT_IMPORT)
    if E2E:
        for study in E2E_GMX_STUDIES:
            ensure_demo_files(study.experiment_id, [study.tpr_name, "structure.pdb", "trajectory.xtc"])
        ensure_amber_demo_files(
            E2E_AMBER_TETRA,
            prmtop_name="tetrapeptide.prmtop",
            inpcrd_name="tetrapeptide.inpcrd",
            mdin_names=["production.mdin"],
        )


def seed_manifests() -> None:
    """Write the simulation manifests."""
    write_gmx_simulation(MEMBRANE, "gpcr_membrane", topology="gpcr_membrane.tpr")

    # The tuner/running-job-linked "md" simulation must be the experiment's most recent
    # activity; the placeholder manifests are back-dated so they never win the ladder.
    write_gmx_simulation(
        ENZYME,
        "npt_equilibration",
        simulation_path="npt_equilibration.simulation.json",
        topology="npt_equilibration.tpr",
    )
    write_gmx_simulation(
        ENZYME,
        "hiv_protease",
        simulation_path="hiv_protease_apo_enzyme_wild_type_production_run_2024.simulation.json",
        topology="hiv_protease_apo_enzyme_wild_type_production_run_2024.tpr",
    )
    write_gmx_simulation(ENZYME, "md", simulation_path="md.simulation.json", topology="production/md.tpr")
    _backdate(ENZYME, ("npt_equilibration", "hiv_protease_apo_enzyme_wild_type_production_run_2024"))

    write_gmx_simulation(
        PUBLISHED, "lysozyme_hewl", simulation_path="lysozyme_hewl.simulation.json", topology="lysozyme_hewl.tpr"
    )

    write_amber_simulation(
        AMBER_FOLDING,
        "villin",
        simulation_path="villin.simulation.json",
        topology="villin.prmtop",
        coordinates="villin.inpcrd",
        control="production.mdin",
    )
    write_amber_simulation(
        AMBER_FOLDING,
        "villin_equilibration",
        simulation_path="equilibration.simulation.json",
        topology="villin.prmtop",
        coordinates="villin.inpcrd",
        control="equilibration.mdin",
    )
    _backdate(AMBER_FOLDING, ("equilibration",))

    write_amber_simulation(
        AMBER_DNA,
        "dna",
        simulation_path="dna.simulation.json",
        topology="dna.prmtop",
        coordinates="dna.inpcrd",
        control="simulation.mdin",
    )

    if E2E:
        for study in E2E_GMX_STUDIES:
            write_gmx_simulation(
                study.experiment_id,
                study.sim_name,
                simulation_path=f"{study.sim_name}.simulation.json",
                topology=study.tpr_name,
            )
        write_amber_simulation(
            E2E_AMBER_TETRA,
            "tetrapeptide",
            simulation_path="tetrapeptide.simulation.json",
            topology="tetrapeptide.prmtop",
            coordinates="tetrapeptide.inpcrd",
            control="production.mdin",
        )


def _backdate(experiment_id: str, stems: tuple[str, ...]) -> None:
    """Back-date placeholder manifests so the job-linked simulation stays most recent."""
    stale = datetime.now() - timedelta(days=1)
    for stem in stems:
        os.utime(DATA_DIR / experiment_id / f"{stem}.simulation.json", (stale.timestamp(), stale.timestamp()))
