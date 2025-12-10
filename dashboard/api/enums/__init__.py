"""Custom enums for the dashboard API."""

from .device_type import DeviceType
from .job_status import JobStatus
from .pod_status import PodStatus

__all__ = [
    "DeviceType",
    "JobStatus",
    "PodStatus",
]
