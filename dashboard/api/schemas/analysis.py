"""
Shapes of mwf analysis result files served by the analysis results route.

Result files are produced by a third-party workflow and served as-is; these
schemas document the closed catalog the dashboard renders.
"""

from typing import Annotated, NotRequired, TypedDict

from pydantic import ConfigDict, Field, with_config

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
