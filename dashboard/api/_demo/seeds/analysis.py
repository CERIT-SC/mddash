"""Seeded analysis jobs: finished ones leave real MDPosit results, running ones finish on a thread."""

import time

from core.enums import AnalysisType, JobStatus
from modules.models import AnalysisJob, Experiment

from ..analysis_data import materialize_analysis, start_analysis_thread
from ..state import build_model, demo_state
from .experiments import AMBER_DNA, AMBER_FOLDING, ENZYME, PUBLISHED

# Longer than the 3s mock submit runtime so the seeded RUNNING analyses stay
# visibly in-flight before completing with real MDPosit outputs.
SEEDED_ANALYSIS_DURATION_SEC = 25.0


def _analysis(
    experiment: Experiment,
    analysis_id: str,
    simulation_path: str,
    analysis_name: AnalysisType,
    files: tuple[str, str, str | None],
) -> AnalysisJob:
    structure, trajectory, topology = files
    return build_model(
        AnalysisJob,
        id=analysis_id,
        experiment=experiment,
        simulation_path=simulation_path,
        analysis_name=analysis_name,
        structure_file=structure,
        trajectory_file=trajectory,
        topology_file=topology,
    )


def seed_analyses(experiments: dict[str, Experiment]) -> dict[AnalysisJob, JobStatus]:
    """Build the analysis jobs with the status each one is seeded in."""
    gmx_files = ("structure.pdb", "trajectory.xtc", None)
    dna_files = ("dna.inpcrd", "trajectory.nc", "dna.prmtop")
    villin_files = ("villin.inpcrd", "trajectory.nc", "villin.prmtop")
    published, enzyme = experiments[PUBLISHED], experiments[ENZYME]
    dna, villin = experiments[AMBER_DNA], experiments[AMBER_FOLDING]
    # Finished ones simulate analyses the user ran earlier; the DNA and villin
    # studies each have one ready and one still calculating.
    return {
        _analysis(published, "analysis-rmsd", "lysozyme_hewl.simulation.json", AnalysisType.RMSDS, gmx_files): (
            JobStatus.FINISHED
        ),
        _analysis(published, "analysis-sasa", "lysozyme_hewl.simulation.json", AnalysisType.SAS, gmx_files): (
            JobStatus.FINISHED
        ),
        _analysis(enzyme, "analysis-hbonds", "md.simulation.json", AnalysisType.HBONDS, gmx_files): JobStatus.FINISHED,
        _analysis(dna, "analysis-dna-rmsd", "dna.simulation.json", AnalysisType.RMSDS, dna_files): JobStatus.FINISHED,
        _analysis(dna, "analysis-dna-clusters", "dna.simulation.json", AnalysisType.CLUSTERS, dna_files): (
            JobStatus.RUNNING
        ),
        _analysis(villin, "analysis-villin-rmsd", "villin.simulation.json", AnalysisType.RMSDS, villin_files): (
            JobStatus.FINISHED
        ),
        _analysis(villin, "analysis-villin-clusters", "villin.simulation.json", AnalysisType.CLUSTERS, villin_files): (
            JobStatus.RUNNING
        ),
    }


def start_analyses(analyses: dict[AnalysisJob, JobStatus]) -> None:
    """Register the seeded analyses with the fake Kubernetes and produce their results."""
    for analysis, status in analyses.items():
        # created_at keeps the job RUNNING on status polls (mirrors what the
        # fake create_job writes for freshly submitted analyses).
        demo_state.analysis_jobs[f"analysis-{analysis.id}"] = {
            "status": status.value,
            "experiment_id": analysis.experiment_id,
            "analysis_name": analysis.analysis_name.value,
            "created_at": time.time(),
        }

    # Seeded FINISHED analyses were "calculated earlier": leave the result
    # files a real run would have left, fetched from MDPosit. Offline, the job
    # records stay FINISHED with no output — the UI shows "produced no data".
    for analysis, status in analyses.items():
        if status is JobStatus.FINISHED:
            materialize_analysis(analysis.experiment_id, analysis.simulation_path, analysis.analysis_name.value)

    # Seeded RUNNING analyses complete like user-submitted ones: after a longer
    # visible runtime the thread writes real MDPosit outputs and flips FINISHED.
    for analysis, status in analyses.items():
        if status is JobStatus.RUNNING:
            start_analysis_thread(
                f"analysis-{analysis.id}",
                analysis.experiment_id,
                analysis.simulation_path,
                analysis.analysis_name.value,
                delay_sec=SEEDED_ANALYSIS_DURATION_SEC,
            )
