"""Custom enums for the dashboard API."""

from core.enums.analysis_type import AnalysisType
from core.enums.device_type import DeviceType
from core.enums.engine import AmberBinary, Engine, EwaldPreset
from core.enums.job_status import JobStatus
from core.enums.notebook_tier import NotebookTier
from core.enums.pod_status import PodStatus
from core.enums.population_status import PopulationStatus
from core.enums.preprocessing_mode import PreprocessingMode
from core.enums.source_type import SourceType

__all__ = [
    "AmberBinary",
    "AnalysisType",
    "DeviceType",
    "Engine",
    "EwaldPreset",
    "JobStatus",
    "NotebookTier",
    "PodStatus",
    "PopulationStatus",
    "PreprocessingMode",
    "SourceType",
]
