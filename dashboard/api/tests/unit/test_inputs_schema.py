"""Unit tests for request-parsing schemas (schemas/inputs.py)."""

import pytest
from enums import AnalysisType, PreprocessingMode
from marshmallow import ValidationError
from schemas.inputs import SubmitAnalysisSchema


class TestSubmitAnalysisSchema:
    """The schema boundary must speak the public contract's enum values."""

    def test_accepts_contract_preprocessing_modes(self) -> None:
        """openapi.yaml declares as_is / image / image_fit — all three must load."""
        expected = {
            "as_is": PreprocessingMode.AS_IS,
            "image": PreprocessingMode.IMAGE,
            "image_fit": PreprocessingMode.IMAGE_FIT,
        }
        for wire_value, member in expected.items():
            data = SubmitAnalysisSchema().load({
                "simulation_path": "md.simulation.json",
                "analysis": "rmsds",
                "preprocessing_mode": wire_value,
            })
            assert data["preprocessing_mode"] is member

    def test_defaults_to_as_is(self) -> None:
        """A missing preprocessing_mode defaults to as_is, matching the contract default."""
        data = SubmitAnalysisSchema().load({"simulation_path": "md.simulation.json", "analysis": "rmsds"})
        assert data["preprocessing_mode"] is PreprocessingMode.AS_IS

    def test_converts_analysis_to_enum(self) -> None:
        data = SubmitAnalysisSchema().load({"simulation_path": "md.simulation.json", "analysis": "rmsds"})
        assert data["analysis"] is AnalysisType.RMSDS

    def test_rejects_unknown_preprocessing_mode_with_available_values(self) -> None:
        """The failure lists the contract values."""
        with pytest.raises(ValidationError, match="as_is, image, image_fit"):
            SubmitAnalysisSchema().load({
                "simulation_path": "md.simulation.json",
                "analysis": "rmsds",
                "preprocessing_mode": "as-is",
            })
