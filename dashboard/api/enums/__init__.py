"""Custom enums for the dashboard API."""

from .analysis_type import AnalysisType
from .device_type import DeviceType
from .job_status import JobStatus
from .pod_status import PodStatus
from .preprocessing_mode import PreprocessingMode

__all__ = [
    "AnalysisType",
    "DeviceType",
    "JobStatus",
    "PodStatus",
    "PreprocessingMode",
]
