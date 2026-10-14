"""Experiment, notebook, publication, and archive schemas."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, NotRequired, TypedDict

from enums import Engine, PodStatus
from enums import NotebookTier as NotebookTierValue
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, with_config

from .common import ArchiveState, FileInfo, OrmModel, enum_schema
from .jobs import AnalysisJob, SimulationJob, TunerJob


class NotebookModuleCategory(str, Enum):
    """Semantic system category of a curated notebook module (drives the card icon)."""

    PROTEIN = "protein"
    MEMBRANE_PROTEIN = "membrane-protein"
    NUCLEIC_ACIDS = "nucleic-acids"
    PROTEIN_LIGAND = "protein-ligand"
    SMALL_MOLECULE = "small-molecule"
    CARBOHYDRATE = "carbohydrate"
    POLYMER = "polymer"


# Stored categories are snapshots: an old row must still serialize if the catalog enum changes.
ModuleCategory = Annotated[
    str | None,
    WithJsonSchema({"anyOf": [{"$ref": "#/components/schemas/NotebookModuleCategory"}, {"type": "null"}]}),
]
Tier = Annotated[NotebookTierValue, WithJsonSchema(enum_schema(NotebookTierValue))]
NullableTier = Annotated[NotebookTierValue | None, WithJsonSchema(enum_schema(NotebookTierValue, nullable=True))]


@with_config(ConfigDict(extra="forbid"))
class NotebookModule(TypedDict):
    """Curated notebook module display metadata (no internal paths or URLs)."""

    id: str
    name: str
    description: NotRequired[str]
    engine: Engine
    author: str
    category: NotebookModuleCategory


class Metrics(BaseModel):
    """Storage usage and server uptime."""

    model_config = ConfigDict(extra="forbid")

    storage_used_bytes: Annotated[
        int | None, Field(description="Bytes used; null until the du monitor records a measurement")
    ]
    storage_limit_bytes: Annotated[int | None, Field(description="Configured storage quota in bytes")]
    uptime_seconds: int


class NotebookTier(BaseModel):
    """A notebook resource tier."""

    model_config = ConfigDict(extra="forbid")

    value: Tier
    cpuLimit: str  # ruff:ignore[mixed-case-variable-in-class-scope]
    memoryLimit: str  # ruff:ignore[mixed-case-variable-in-class-scope]


class NotebookConfig(BaseModel):
    """Notebook tiers, the default tier, and the concurrent-notebook limit."""

    model_config = ConfigDict(extra="forbid")

    tiers: Annotated[list[NotebookTier], Field(min_length=1)]
    defaultTier: Tier  # ruff:ignore[mixed-case-variable-in-class-scope]
    concurrentLimit: Annotated[  # ruff:ignore[mixed-case-variable-in-class-scope]
        int, Field(ge=1, description="Max concurrent notebook pods per user namespace")
    ]


class Notebook(OrmModel):
    """The experiment's JupyterLab notebook."""

    id: int
    experiment_id: str
    token: str
    tier: NullableTier = None
    gpu: bool
    path: str
    status: PodStatus
    started_at: Annotated[datetime | None, Field(description="Pod start time; null while the pod is absent")]


class StartNotebookRequest(BaseModel):
    """Notebook start options."""

    model_config = ConfigDict(extra="forbid")

    tier: Tier | None = None
    gpu: bool = False


@with_config(ConfigDict(extra="forbid"))
class ExperimentSource(TypedDict):
    """Structured experiment provenance."""

    type: Literal["pdb", "repo", "file"]
    pdb_id: NotRequired[str]
    url: NotRequired[str]
    files: list[FileInfo]
    file_count: NotRequired[Annotated[int, Field(ge=0)]]


class Experiment(OrmModel):
    """A molecular dynamics experiment with its notebook and jobs."""

    id: str
    created_at: datetime
    updated_at: datetime
    name: str
    module_name: str | None = None
    # Category snapshot of the curated module; null = custom workflow.
    module_category: ModuleCategory = None
    # Manifest path of the most recently active simulation; the experiment's
    # step/status and dashboard detail rows always inherit from it.
    latest_simulation_path: str | None
    source: ExperimentSource | None = None
    size_bytes: int | None = None
    notebooks_repo: str | None = None
    mdrepo_id: str | None = None
    mdrepo_published: bool | None = None
    engine: Engine
    notebook: Notebook | None
    tuner_jobs: list[TunerJob]
    simulation_jobs: list[SimulationJob]
    analysis_jobs: list[AnalysisJob]
    step: int = 0
    status: str = "setup"
    # Archive lifecycle: archived_at null = active experiment. While archived,
    # step/status/size_bytes serve the snapshot taken at archive time.
    archived_at: datetime | None
    archive_state: ArchiveState | None
    # Publishing is experiment-level: true once a draft exists or any run finished.
    can_publish: bool = False
    mdrepo_record_url: str | None = None


class UpdateExperiment(BaseModel):
    """Editable experiment properties."""

    model_config = ConfigDict(extra="forbid")

    name: str


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


@with_config(ConfigDict(extra="forbid"))
class ArchiveAttempt(TypedDict):
    """Accepted archive or restore."""

    attempt_id: str


@with_config(ConfigDict(extra="forbid"))
class ArchiveStatus(TypedDict):
    """Archive/restore state reconciled with live Jobs."""

    experiment_id: str
    archive_state: ArchiveState | None
    attempt_id: str | None
    direction: Literal["archive", "restore"] | None
    reason: str | None


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


@with_config(ConfigDict(extra="forbid"))
class MDRepoStatus(TypedDict):
    """MDRepo authentication status."""

    authenticated: bool
    mdrepo_url: NotRequired[str]
