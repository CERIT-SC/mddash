"""
MetaDump API client for extracting metadata from GROMACS TPR files.
"""

import logging
import time
from pathlib import Path

import requests
from config import METADUMP_API_URL
from werkzeug.exceptions import InternalServerError

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5
TIMEOUT_SEC = 150
MAX_POLLS = TIMEOUT_SEC // POLL_INTERVAL_SEC


def extract_metadata_bulk(tpr_paths: list[Path]) -> list[dict]:
    """
    Extract metadata from multiple TPR files via the MetaDump API.

    Uploads all files, polls until all jobs complete, fetches results,
    then cleans up remote jobs. Results are returned in the same order
    as the input paths.

    Args:
        tpr_paths: List of paths to GROMACS TPR files.

    Returns:
        List of metadata dicts, one per input path, in the same order.

    Raises:
        InternalServerError: If any upload fails, any job enters error
            status, or the polling timeout is exceeded.
    """
    if METADUMP_API_URL is None:
        return []

    if not tpr_paths:
        return []

    # uuid -> pin, preserved for cleanup
    uuid_to_pin: dict[str, str] = {}
    # Tracks submission order so results are returned in input order
    uuid_order: list[str] = []

    for path in tpr_paths:
        with path.open("rb") as f:
            response = requests.post(
                f"{METADUMP_API_URL}/api/annotate",
                files={"file": (path.name, f, "application/octet-stream")},
                timeout=60,
            )

        if not response.ok:
            raise InternalServerError(
                description=f"MetaDump upload failed for '{path.name}': {response.status_code} - {response.text}"
            )

        try:
            data = response.json()
        except ValueError:
            raise InternalServerError(
                description=f"MetaDump returned non-JSON response for '{path.name}'"
            )
        uuid = data.get("uuid")
        pin = data.get("pin")

        if not uuid or not pin:
            raise InternalServerError(
                description=f"MetaDump returned unexpected response for '{path.name}': {data}"
            )

        uuid_to_pin[uuid] = pin
        uuid_order.append(uuid)
        logger.info("MetaDump job submitted for '%s': uuid=%s", path.name, uuid)

    pending: set[str] = set(uuid_order)
    completed: set[str] = set()

    try:
        for _ in range(MAX_POLLS):
            time.sleep(POLL_INTERVAL_SEC)

            for uuid in list(pending):
                response = requests.get(
                    f"{METADUMP_API_URL}/api/annotate/{uuid}",
                    timeout=30,
                )

                if not response.ok:
                    raise InternalServerError(
                        description=f"MetaDump status check failed for uuid={uuid}: {response.status_code} - {response.text}"
                    )

                try:
                    status = response.json().get("status")
                except ValueError:
                    raise InternalServerError(
                        description=f"MetaDump returned non-JSON status response for uuid={uuid}"
                    )

                match status:
                    case "completed":
                        pending.discard(uuid)
                        completed.add(uuid)
                        logger.info("MetaDump job completed: uuid=%s", uuid)
                    case "error":
                        raise InternalServerError(
                            description=f"MetaDump job failed with error status: uuid={uuid}"
                        )
                    case "pending" | "running":
                        pass
                    case _:
                        raise InternalServerError(
                            description=f"MetaDump job returned unknown status '{status}': uuid={uuid}"
                        )

            if not pending:
                break
        else:
            raise InternalServerError(
                description=f"MetaDump timed out after {TIMEOUT_SEC} seconds waiting for jobs to complete"
            )

        results: dict[str, dict] = {}
        for uuid in completed:
            response = requests.get(
                f"{METADUMP_API_URL}/api/annotate/{uuid}/results",
                timeout=30,
            )

            if not response.ok:
                raise InternalServerError(
                    description=f"MetaDump results fetch failed for uuid={uuid}: {response.status_code} - {response.text}"
                )

            results[uuid] = response.json()
            logger.info("MetaDump results fetched: uuid=%s", uuid)

    finally:
        for uuid, pin in uuid_to_pin.items():
            try:
                response = requests.delete(
                    f"{METADUMP_API_URL}/api/annotate/{uuid}",
                    params={"pin": pin},
                    timeout=30,
                )
                if not response.ok:
                    logger.warning("MetaDump cleanup failed for uuid=%s: %s", uuid, response.status_code)
            except requests.RequestException:
                logger.warning("MetaDump cleanup request error for uuid=%s", uuid, exc_info=True)

    return [results[uuid] for uuid in uuid_order]


def extract_metadata(tpr_path: Path) -> dict:
    """
    Extract metadata from a single TPR file via the MetaDump API.

    Args:
        tpr_path: Path to the GROMACS TPR file.

    Returns:
        Metadata dict for the file.

    Raises:
        InternalServerError: If the extraction fails.
    """
    results = extract_metadata_bulk([tpr_path])
    return results[0]
