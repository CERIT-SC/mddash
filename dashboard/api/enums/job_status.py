from enum import Enum

class JobStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"

    def __str__(self):
        return self.value
    
    @classmethod
    def from_string(cls, value: str) -> 'JobStatus':
        return cls(value.upper())
