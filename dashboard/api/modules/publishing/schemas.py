"""Publication schemas (MDRepo drafts and MDPosit packages)."""

from typing import Annotated, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, with_config


class PublishRequest(BaseModel):
    """Publication target (MDPosit requires the simulation to publish)."""

    model_config = ConfigDict(extra="forbid")

    target: Literal["invenio", "mdposit"] = "invenio"
    simulation_path: str | None = None


@with_config(ConfigDict(extra="forbid"))
class MDRepoPublication(TypedDict):
    """Accepted MDRepo draft upload."""

    id: str
    links: dict[str, str]
    upload_id: str
    upload_state: str
    draft_url: str | None


@with_config(ConfigDict(extra="forbid"))
class PublicationFile(TypedDict):
    """A file of an MDPosit publication package."""

    role: NotRequired[str]
    path: str
    url: str


@with_config(ConfigDict(extra="forbid"))
class MDPositPublication(TypedDict):
    """MDPosit publication package handed to VRE Lite."""

    metadata_file: PublicationFile
    files: list[PublicationFile]
    vre_lite_url: str | None


@with_config(ConfigDict(extra="allow"))
class FailedUploadFile(TypedDict):
    """A file that failed to upload."""

    key: str
    error: str


@with_config(ConfigDict(extra="allow"))
class PublishStatus(TypedDict):
    """Durable MDRepo upload status merged with live Job state."""

    experiment_id: str
    mdrepo_id: str | None
    draft_url: str | None
    upload_state: str | None
    reason: str | None
    total_files: Annotated[int, Field(ge=0)]
    completed_files: Annotated[int, Field(ge=0)]
    total_bytes: Annotated[int, Field(ge=0)]
    completed_bytes: Annotated[int, Field(ge=0)]
    upload_attempt_id: NotRequired[str]
    failed_files: NotRequired[list[FailedUploadFile]]
