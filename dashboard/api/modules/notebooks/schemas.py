"""Notebook, notebook tier, and curated notebook module schemas."""

from datetime import datetime
from enum import Enum
from typing import Annotated, NotRequired, TypedDict

from core.enums import Engine, PodStatus
from core.enums import NotebookTier as NotebookTierValue
from core.schemas import OrmModel, enum_schema
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, with_config


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
