"""One-shot Datahugger-NG population worker Job submission (deterministic name, no credentials)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.config import API_IMAGE, MAX_NOTEBOOKS
from core.worker_jobs import EXPERIMENT_LABEL, SubmissionError, delete_worker_job, dns1123_name, worker_job_manifest

if TYPE_CHECKING:
    from clients.k8s import K8sClient

    from modules.population.models import PopulationOperation

logger = logging.getLogger(__name__)

POPULATION_APP_LABEL = "datahugger-populate"
POPULATION_ADMISSION_TIMEOUT = 30  # seconds


def job_name(operation_id: str) -> str:
    """Deterministic name for an operation's population Job."""
    return dns1123_name("datahugger-populate", operation_id)


def build_job_manifest(operation: PopulationOperation) -> dict[str, Any]:
    """
    Worker Job on the shared PVC running the API image's population worker.

    Carries the public repository URL and non-secret configuration: no notebook token or credentials.
    """
    return worker_job_manifest(
        name=operation.job_name,
        app=POPULATION_APP_LABEL,
        experiment_id=operation.experiment_id,
        container="population",
        image=API_IMAGE,
        command=["python", "-m", "modules.population.worker"],
        args=[
            "--operation-id",
            operation.id,
            "--experiment-id",
            operation.experiment_id,
            "--repo-url",
            operation.repo_url,
        ],
        env=[{"name": "NS_MAX_NOTEBOOKS", "value": str(MAX_NOTEBOOKS)}],
    )


async def submit_population_job(k8s: K8sClient, operation: PopulationOperation) -> None:
    """Create the worker Job and wait for pod admission (raises SubmissionError, cleaning up on failure)."""
    if not API_IMAGE:
        raise SubmissionError("API_IMAGE is not set. Redeploy the Helm chart and restart the server.")
    try:
        await k8s.create_job_raw(build_job_manifest(operation))
        label_selector = f"{EXPERIMENT_LABEL}={operation.experiment_id}"
        if not await k8s.wait_for_pod_admission(label_selector, max_wait=POPULATION_ADMISSION_TIMEOUT):
            logger.error("Pod admission timeout for population Job %s", operation.job_name)
            raise SubmissionError(f"Population pod not admitted within {POPULATION_ADMISSION_TIMEOUT}s")
        logger.info("Population Job %s admitted for experiment %s", operation.job_name, operation.experiment_id)
    except SubmissionError:
        await delete_population_resources(k8s, operation)
        raise
    except Exception as e:
        logger.error("Failed to submit population Job %s: %s", operation.job_name, e)
        await delete_population_resources(k8s, operation)
        raise SubmissionError("Failed to submit the population worker Job.") from e


async def delete_population_resources(k8s: K8sClient, operation: PopulationOperation) -> bool:
    """Foreground-delete the population Job; True only once its absence is confirmed."""
    return await delete_worker_job(k8s, operation.job_name)
