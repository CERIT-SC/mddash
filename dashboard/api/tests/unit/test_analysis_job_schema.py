"""Unit tests for AnalysisJobSchema response serialization."""

from enums import AnalysisType
from models import AnalysisJob
from schemas.analysis_job import AnalysisJobSchema


def test_analysis_name_serialized_by_value() -> None:
    """Response analysis_name must be the enum value, not the name (UI compares with catalog values)."""
    job = AnalysisJob(
        id="x",
        experiment_id="exp-test",
        simulation_path="md.simulation.json",
        analysis_name=AnalysisType.RMSDS,
    )  # type: ignore[call-arg]
    dumped = AnalysisJobSchema().dump(job)
    assert dumped["analysis_name"] == "rmsds"
