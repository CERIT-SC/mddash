"""
Analysis job schemas and the shapes of mwf analysis result files.

Result files are produced by a third-party workflow and served as-is; these
schemas document the closed catalog the dashboard renders.
"""

from datetime import datetime
from typing import Annotated, NotRequired, TypedDict

from core.enums import AnalysisType, JobStatus, PreprocessingMode
from core.schemas import OrmModel, enum_schema
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, with_config

AnalysisName = Annotated[AnalysisType, WithJsonSchema(enum_schema(AnalysisType))]
Preprocessing = Annotated[PreprocessingMode, WithJsonSchema(enum_schema(PreprocessingMode))]


class AnalysisJob(OrmModel):
    """On-demand mwf analysis job (input file paths pass through)."""

    model_config = ConfigDict(extra="allow")

    id: str
    experiment_id: str
    simulation_path: str
    analysis_name: AnalysisName
    created_at: datetime
    status: JobStatus
    sim_progress: Annotated[
        float | None,
        Field(
            description="Fraction (0-1) of the simulation's steps available when the analysis inputs were snapshotted; null when unknown."
        ),
    ] = None
    structure_file: str | None = None
    trajectory_file: str | None = None
    topology_file: str | None = None


class AnalysisJobRequest(BaseModel):
    """Analysis of a simulation's trajectory."""

    model_config = ConfigDict(extra="forbid")

    simulation_path: Annotated[str, Field(min_length=1)]
    analysis: AnalysisName
    preprocessing_mode: Preprocessing = PreprocessingMode.AS_IS


@with_config(ConfigDict(extra="allow"))
class AnalysisVariant(TypedDict):
    """One variant of a multi-file analysis (extra summary keys pass through)."""

    analysis: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]


type NumberMatrix = list[list[float]]
type BooleanMatrix = list[list[bool]]

_forbid = with_config(ConfigDict(extra="forbid"))
_allow = with_config(ConfigDict(extra="allow"))


@_forbid
class StatisticalData(TypedDict):
    """Summary statistics of a series."""

    average: float
    stddev: float
    min: float
    max: float
    data: list[float]


@_forbid
class StatisticalSeriesResult(TypedDict):
    """Per-key statistical series."""

    start: NotRequired[float]
    step: float
    y: Annotated[dict[str, StatisticalData], Field(min_length=1)]


@_forbid
class NamedSeriesResultDataItem(TypedDict):
    """One reference/group series."""

    reference: str
    group: str
    values: list[float]


@_forbid
class NamedSeriesResult(TypedDict):
    """Series keyed by reference and group."""

    start: float
    step: float
    data: list[NamedSeriesResultDataItem]


@_allow
class NamedDataResultDataItem(TypedDict):
    """One named data entry."""

    name: str


@_forbid
class NamedDataResult(TypedDict):
    """Named data entries."""

    step: NotRequired[float]
    data: list[NamedDataResultDataItem]


@with_config(
    ConfigDict(extra="forbid", json_schema_extra={"anyOf": [{"required": ["rmsdpr"]}, {"required": ["saspf"]}]})
)
class MatrixResult(TypedDict):
    """Per-residue matrix (RMSD per residue or SASA per frame)."""

    start: NotRequired[float]
    step: NotRequired[float]
    rmsdpr: NotRequired[NumberMatrix]
    saspf: NotRequired[list[list[float | None]]]
    means: NotRequired[list[float]]
    stdvs: NotRequired[list[float]]


@_forbid
class PCAResult(TypedDict):
    """Principal component analysis."""

    framestep: float
    atoms: list[int]
    eigenvalues: list[float]
    projections: NumberMatrix


@_forbid
class ClustersResultClustersItem(TypedDict):
    """One cluster."""

    frames: list[int]
    main: int


# Functional syntax: "from" is a keyword.
ClustersResultTransitionsItem = _forbid(
    TypedDict("ClustersResultTransitionsItem", {"from": int, "to": int, "count": int})
)


@_forbid
class ClustersResult(TypedDict):
    """Conformational clusters and their transitions."""

    name: str
    cutoff: float
    clusters: list[ClustersResultClustersItem]
    transitions: list[ClustersResultTransitionsItem]
    step: float
    version: str


@_forbid
class MembraneMapResult(TypedDict):
    """Membrane assignment of lipids."""

    n_mems: int
    mems: dict[str, dict]
    no_mem_lipid: list[int]


@_forbid
class ThicknessResult(TypedDict):
    """Membrane thickness over time."""

    step: NotRequired[float]
    data: dict[str, list[float]]


@_allow
class InteractionResult(TypedDict):
    """Interaction between two agents."""

    name: str
    agent_1: str
    agent_2: str
    has_cg: NotRequired[bool]
    version: NotRequired[str]


type AnalysisResult = (
    StatisticalSeriesResult
    | NamedSeriesResult
    | NamedDataResult
    | MatrixResult
    | PCAResult
    | ClustersResult
    | MembraneMapResult
    | ThicknessResult
    | InteractionResult
)
