"""Unit tests for request parsing and response serialization schemas."""

from datetime import UTC, datetime

import pytest
from enums import AnalysisType, DeviceType, Engine, JobStatus, NotebookTier, PodStatus, PreprocessingMode
from models import AnalysisJob, Experiment, GromacsJob, Notebook
from pydantic import ValidationError
from schemas.experiment import Notebook as NotebookOut
from schemas.jobs import AnalysisJob as AnalysisJobOut
from schemas.jobs import AnalysisJobRequest, GromacsJobRequest
from schemas.jobs import SimulationJob as SimulationJobOut


class TestAnalysisJobRequest:
    """The schema boundary must speak the public contract's enum values."""

    @pytest.mark.parametrize(
        ("wire_value", "member"),
        [
            ("as_is", PreprocessingMode.AS_IS),
            ("image", PreprocessingMode.IMAGE),
            ("image_fit", PreprocessingMode.IMAGE_FIT),
        ],
    )
    def test_accepts_contract_preprocessing_modes(self, wire_value: str, member: PreprocessingMode) -> None:
        request = AnalysisJobRequest.model_validate({
            "simulation_path": "md.simulation.json",
            "analysis": "rmsds",
            "preprocessing_mode": wire_value,
        })
        assert request.preprocessing_mode is member

    def test_defaults_to_as_is(self) -> None:
        """A missing preprocessing_mode defaults to as_is, matching the contract default."""
        request = AnalysisJobRequest.model_validate({"simulation_path": "md.simulation.json", "analysis": "rmsds"})
        assert request.preprocessing_mode is PreprocessingMode.AS_IS

    def test_converts_analysis_to_enum(self) -> None:
        request = AnalysisJobRequest.model_validate({"simulation_path": "md.simulation.json", "analysis": "rmsds"})
        assert request.analysis is AnalysisType.RMSDS

    def test_rejects_unknown_preprocessing_mode(self) -> None:
        with pytest.raises(ValidationError, match="preprocessing_mode"):
            AnalysisJobRequest.model_validate({
                "simulation_path": "md.simulation.json",
                "analysis": "rmsds",
                "preprocessing_mode": "as-is",
            })

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            AnalysisJobRequest.model_validate({"simulation_path": "md.simulation.json", "analysis": "rmsds", "x": 1})


def test_gromacs_request_rejects_auto_device_and_non_positive_counts() -> None:
    """Only the contract devices (cpu/gpu) and positive process counts are accepted."""
    with pytest.raises(ValidationError):
        GromacsJobRequest.model_validate({"np": 1, "ntomp": 1, "pme": "auto", "nb": "cpu"})
    with pytest.raises(ValidationError):
        GromacsJobRequest.model_validate({"np": 0, "ntomp": 1, "pme": "cpu", "nb": "cpu"})
    assert DeviceType(GromacsJobRequest(np=1, ntomp=2, pme="gpu", nb="cpu").pme) is DeviceType.GPU


def test_analysis_name_serialized_by_value() -> None:
    """Response analysis_name must be the enum value, not the name (UI compares with catalog values)."""
    job = AnalysisJob(
        id="x",
        experiment_id="exp-test",
        simulation_path="md.simulation.json",
        analysis_name=AnalysisType.RMSDS,
        trajectory_file="traj.xtc",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        _last_known_status=JobStatus.FINISHED,
    )
    dumped = AnalysisJobOut.model_validate(job).model_dump(mode="json")
    assert dumped["analysis_name"] == "rmsds"
    assert dumped["status"] == "FINISHED"


def test_notebook_tier_serialized_by_value() -> None:
    """Notebook tier dumps as "2x", never as the member name."""
    notebook = Notebook(id=1, experiment_id="abcde", token="t", tier=NotebookTier.MEDIUM, gpu=False)
    notebook._pod_info = (PodStatus.RUNNING, None)
    dumped = NotebookOut.model_validate(notebook).model_dump(mode="json")
    assert dumped["tier"] == "2x"
    assert dumped["status"] == "RUNNING"


def test_failing_property_falls_back_to_default() -> None:
    """A run whose manifest is gone still serializes; file-derived values fall back to null."""
    job = GromacsJob(
        id="run1",
        experiment_id="abcde",
        experiment=Experiment(id="abcde", name="E"),
        simulation_path="deleted.simulation.json",
        engine=Engine.GMX,
        np=1,
        ntomp=1,
        pme=DeviceType.CPU,
        nb=DeviceType.CPU,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    job._fetched_status = JobStatus.RUNNING

    dumped = SimulationJobOut.model_validate(job).model_dump(mode="json")

    assert dumped["status"] == "RUNNING"
    assert dumped["start_timestamp"] is None
    assert dumped["nsteps_done"] is None
