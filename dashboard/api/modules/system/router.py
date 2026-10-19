import time
from typing import Literal

from clients.k8s import parse_memory
from core.config import API_PREFIX, DATA_DIR, MAX_NOTEBOOKS, PVC_SIZE
from core.enums import NotebookTier as NotebookTierValue
from core.responses import problems
from core.utils import get_du_size
from fastapi import APIRouter
from pydantic import TypeAdapter

from modules.notebooks.catalog import load_catalog
from modules.notebooks.models import get_tier_resources
from modules.notebooks.schemas import NotebookConfig, NotebookModule, NotebookTier
from modules.system.schemas import Metrics

router = APIRouter(prefix=API_PREFIX)

# The API sidecar starts with the user server pod, so process uptime ≈ server uptime.
_STARTED_AT = time.monotonic()

Health = Literal["API is up!"]
_modules = TypeAdapter(list[NotebookModule])


@router.get(
    "/", tags=["System"], summary="Check API health", operation_id="getApiRoot", response_description="API is running"
)
async def index() -> Health:
    """Health check."""
    return "API is up!"


@router.get(
    "/health",
    tags=["System"],
    summary="Check API health",
    operation_id="getHealth",
    response_description="API is running",
)
async def health() -> Health:
    """Health check."""
    return "API is up!"


@router.get(
    "/notebook-modules",
    tags=["Notebooks"],
    summary="List curated notebook modules",
    operation_id="listNotebookModules",
    response_description="Public notebook module catalog",
    responses=problems(),
)
async def get_notebook_modules() -> list[NotebookModule]:
    """Curated notebook module display metadata (no internal paths or URLs)."""
    return _modules.validate_python(load_catalog().to_public())


@router.get(
    "/metrics",
    tags=["System"],
    summary="Get resource usage and limits",
    operation_id="getMetrics",
    response_description="Resource metrics",
    responses=problems(),
)
async def get_metrics() -> Metrics:
    """Storage used/limit in bytes (used is null until the du monitor measures) and server uptime."""
    return Metrics(
        storage_used_bytes=get_du_size(DATA_DIR),
        storage_limit_bytes=parse_memory(PVC_SIZE),
        uptime_seconds=round(time.monotonic() - _STARTED_AT),
    )


@router.get(
    "/notebook-config",
    tags=["Notebooks"],
    summary="Get notebook resource configuration",
    operation_id="getNotebookConfig",
    response_description="Notebook tiers and default",
    responses=problems(),
)
async def get_notebook_config() -> NotebookConfig:
    """Available notebook resource tiers, the default tier, and the concurrent-notebook limit."""
    tiers = []
    for tier in NotebookTierValue:
        resources = get_tier_resources(tier)
        tiers.append(
            NotebookTier(value=tier, cpuLimit=resources["limits"]["cpu"], memoryLimit=resources["limits"]["memory"])
        )
    return NotebookConfig(tiers=tiers, defaultTier=NotebookTierValue.SMALL, concurrentLimit=MAX_NOTEBOOKS)
