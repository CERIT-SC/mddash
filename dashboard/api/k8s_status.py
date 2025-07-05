from enum import Enum


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"

    def __str__(self):
        return self.value
    
    @classmethod
    def from_string(cls, value: str) -> 'JobStatus':
        return cls(value.upper())


class PodStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    DOWN = "DOWN"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"

    def __str__(self):
        return self.value
    
    @classmethod
    def from_string(cls, value: str) -> 'PodStatus':
        return cls(value.upper())
