"""MetaDump API client for extracting metadata from GROMACS TPR files."""

import asyncio
import logging
from pathlib import Path

import anyio
import httpx
from config import METADUMP_API_URL
from errors import InternalServerError

from clients.http import client

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5
TIMEOUT_SEC = 150
MAX_POLLS = TIMEOUT_SEC // POLL_INTERVAL_SEC


async def _submit_job(tpr_path: Path) -> tuple[str, str]:
    content = await anyio.Path(tpr_path).read_bytes()
    response = await client().post(
        f"{METADUMP_API_URL}/api/annotate",
        files={"file": (tpr_path.name, content, "application/octet-stream")},
        timeout=60,
    )
    if not response.is_success:
        raise InternalServerError(f"MetaDump upload failed for '{tpr_path.name}' (HTTP {response.status_code}).")

    try:
        data = response.json()
    except ValueError:
        raise InternalServerError(f"MetaDump returned non-JSON response for '{tpr_path.name}'")

    uuid = data.get("uuid")
    pin = data.get("pin")
    if not uuid or not pin:
        raise InternalServerError(f"MetaDump returned unexpected response for '{tpr_path.name}'.")
    return uuid, pin


async def _poll_status(uuid: str) -> str:
    response = await client().get(f"{METADUMP_API_URL}/api/annotate/{uuid}", timeout=30)
    if not response.is_success:
        raise InternalServerError(f"MetaDump status check failed for uuid={uuid} (HTTP {response.status_code}).")
    try:
        return response.json().get("status")
    except ValueError:
        raise InternalServerError(f"MetaDump returned non-JSON status response for uuid={uuid}")


async def _fetch_results(uuid: str) -> dict:
    response = await client().get(f"{METADUMP_API_URL}/api/annotate/{uuid}/results", timeout=30)
    if not response.is_success:
        raise InternalServerError(f"MetaDump results fetch failed for uuid={uuid} (HTTP {response.status_code}).")
    return response.json()


def _is_job_complete(uuid: str, status: str) -> bool:
    match status:
        case "completed":
            return True
        case "error":
            raise InternalServerError(f"MetaDump job failed with error status: uuid={uuid}")
        case "pending" | "running":
            return False
        case _:
            raise InternalServerError(f"MetaDump job returned unknown status '{status}': uuid={uuid}")


async def _delete_job(uuid: str, pin: str) -> None:
    try:
        response = await client().delete(f"{METADUMP_API_URL}/api/annotate/{uuid}", params={"pin": pin}, timeout=30)
        if not response.is_success:
            logger.warning("MetaDump cleanup failed for uuid=%s: %s", uuid, response.status_code)
    except httpx.HTTPError:
        logger.warning("MetaDump cleanup request error for uuid=%s", uuid, exc_info=True)


async def extract_metadata_bulk(tpr_paths: list[Path]) -> list[dict]:
    """
    Extract metadata from TPR files via MetaDump, in input order.

    Uploads all files, polls until all jobs complete, fetches results, then
    cleans up the remote jobs.

    Raises:
        InternalServerError: If an upload fails, a job errors, or polling times out.
    """
    if METADUMP_API_URL is None or not tpr_paths:
        return []

    uuid_to_pin: dict[str, str] = {}
    uuid_order: list[str] = []
    try:
        for path in tpr_paths:
            uuid, pin = await _submit_job(path)
            uuid_to_pin[uuid] = pin
            uuid_order.append(uuid)
            logger.info("MetaDump job submitted for '%s': uuid=%s", path.name, uuid)

        pending: set[str] = set(uuid_order)
        for _ in range(MAX_POLLS):
            await asyncio.sleep(POLL_INTERVAL_SEC)
            for uuid in list(pending):
                if _is_job_complete(uuid, await _poll_status(uuid)):
                    pending.discard(uuid)
                    logger.info("MetaDump job completed: uuid=%s", uuid)
            if not pending:
                break
        else:
            raise InternalServerError(f"MetaDump timed out after {TIMEOUT_SEC} seconds waiting for jobs to complete")

        results = [await _fetch_results(uuid) for uuid in uuid_order]
        logger.info("MetaDump results fetched for %d job(s)", len(results))
    finally:
        for uuid, pin in uuid_to_pin.items():
            await _delete_job(uuid, pin)

    return results


async def extract_metadata(tpr_path: Path) -> dict:
    """Extract metadata from a single TPR file via MetaDump."""
    return (await extract_metadata_bulk([tpr_path]))[0]
