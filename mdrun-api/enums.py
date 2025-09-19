from enum import Enum


class DeviceType(str, Enum):
    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"

    def __str__(self):
        return self.value
    
    @classmethod
    def from_string(cls, value: str) -> 'DeviceType':
        return cls(value.lower())


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    TERMINATED = "terminated"
    ERROR = "error"
    UNKNOWN = "unknown"

    def __str__(self):
        return self.value
