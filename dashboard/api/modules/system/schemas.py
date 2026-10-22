"""System schemas."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Metrics(BaseModel):
    """Storage usage and server uptime."""

    model_config = ConfigDict(extra="forbid")

    storage_used_bytes: Annotated[
        int | None, Field(description="Bytes used; null until the du monitor records a measurement")
    ]
    storage_limit_bytes: Annotated[int | None, Field(description="Configured storage quota in bytes")]
    uptime_seconds: int
