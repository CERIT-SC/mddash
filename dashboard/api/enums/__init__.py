"""Custom enums for the dashboard API."""

from .analysis_type import AnalysisType
from .device_type import DeviceType
from .engine import AmberBinary, Engine, EwaldPreset
from .job_status import JobStatus
from .notebook_tier import NotebookTier
from .pod_status import PodStatus
from .preprocessing_mode import PreprocessingMode

__all__ = [
    "AmberBinary",
    "AnalysisType",
    "DeviceType",
    "Engine",
    "EwaldPreset",
    "JobStatus",
    "NotebookTier",
    "PodStatus",
    "PreprocessingMode",
]
