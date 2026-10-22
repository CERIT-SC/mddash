"""Experiment schemas."""

from datetime import datetime
from typing import Annotated, Literal, NotRequired, TypedDict

from core.enums import Engine
from core.schemas import ArchiveState, FileInfo, OrmModel
from pydantic import BaseModel, ConfigDict, Field, with_config

from modules.jobs.analysis.schemas import AnalysisJob
from modules.jobs.schemas import SimulationJob
from modules.jobs.tuner.schemas import TunerJob
from modules.notebooks.schemas import ModuleCategory, Notebook


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
