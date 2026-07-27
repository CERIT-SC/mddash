import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasicCredentials

from api.auth import verify_credentials
from api.config import MAX_REQUEST_SIZE
from api.middleware import RequestSizeLimitMiddleware
from api.routers.amber import router as amber_router
from api.routers.gmx import router as gmx_router
from api.schemas.common import HealthResponse, ResourcesResponse
from api.utils import get_cluster_status

logger = logging.getLogger(__name__)

app = FastAPI(title="MD Tuner API", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=MAX_REQUEST_SIZE)

app.include_router(gmx_router, prefix="/api/tuning-jobs/gmx")
app.include_router(amber_router, prefix="/api/tuning-jobs/amber")


@app.get("/api/resources")
async def get_cluster_resources_endpoint(
    _: Annotated[HTTPBasicCredentials, Depends(verify_credentials)],
) -> ResourcesResponse:
    """
    Get current Ray cluster resource utilization.

    Raises:
        HTTPException: 503 if Ray cluster resources are unavailable.
    """
    resources = await get_cluster_status()
    if resources is None:
        raise HTTPException(status_code=503, detail="Cluster resources unavailable - Ray may not be initialized")
    return resources


@app.get("/api/health")
async def health_check() -> HealthResponse:
    """Return a liveness check response."""
    return HealthResponse(status="ok")
