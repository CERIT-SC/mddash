import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import requests
from config import DATA_DIR
from enums import JobStatus
from models.analysis_job import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, mwf_output_dir

from .state import demo_state

logger = logging.getLogger(__name__)

MDPOSIT_ANALYSES_URL = "https://mdposit.mddbr.eu/api/rest/v1/projects/MD-A003ZT.2/analyses"

# AnalysisType (and mwf -i flags) vs MDPosit endpoint names.
MDPOSIT_NAME_MAP: dict[str, str] = {
    "dist": "dist-perres",
    "inter": "interactions",
    "linter": "lipid-inter",
    "lorder": "lipid-order",
    "pairwise": "rmsd-pairwise",
    "perres": "rmsd-perres",
    "rmsf": "fluctuation",
    "sas": "sasa",
    "tmscore": "tmscores",
}

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None


def _summary_variant_names(summary: JsonValue) -> list[str]:
    """Variant endpoint names referenced by a summary-list payload."""
    variants: list[str] = []
    if not isinstance(summary, list):
        return variants
    for item in summary:
        if not isinstance(item, dict):
            continue
        variant = item.get("analysis")
        # Only safe path segments — upstream data flows into file names.
        if isinstance(variant, str) and re.fullmatch(r"[\w-]+", variant):
            variants.append(variant)
    return variants


ANALYSIS_CACHE_DIR = Path(os.environ.get("MDDASH_DEMO_ANALYSIS_CACHE", Path.home() / ".cache" / "mddash-demo"))


def fetch_analysis_payload(mdposit_name: str) -> JsonValue:
    """Get one MDPosit analysis payload, using the on-disk cache when present."""
    cache_file = ANALYSIS_CACHE_DIR / "MD-A003ZT.2" / f"{mdposit_name}.json"
    if cache_file.is_file():
        try:
            return json.loads(cache_file.read_text())
        except (OSError, json.JSONDecodeError):
            cache_file.unlink(missing_ok=True)

    response = requests.get(
        f"{MDPOSIT_ANALYSES_URL}/{mdposit_name}", headers={"Accept": "application/json"}, timeout=30
    )
    if not response.ok:
        logger.warning("Failed to fetch %s from MDposit: %s", mdposit_name, response.status_code)
        return None

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(response.text)
    return response.json()


def write_analysis_result(experiment_id: str, simulation_path: str, mdposit_name: str, data: JsonValue) -> Path:
    """Write one payload as the mwf result file the real routes serve."""
    result_file = (
        DATA_DIR
        / experiment_id
        / mwf_output_dir(simulation_path)
        / (f"{ANALYSIS_RESULT_PREFIX}{mdposit_name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}")
    )
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(data), encoding="utf-8")
    return result_file


def materialize_analysis(experiment_id: str, simulation_path: str, analysis_name: str) -> bool:
    """
    Fetch one analysis from MDPosit and write every file a finished mwf job would leave.

    Writes the base payload, and for summary documents every numbered variant
    too. Returns False when the upstream has no such payload (a real mwf run
    would fail the same way).
    """
    # Use the mwf output name (= MDPosit endpoint name), not the
    # AnalysisType value: "-i inter" produces mda.interactions.json.
    mdposit_name = MDPOSIT_NAME_MAP.get(analysis_name, analysis_name)
    data = fetch_analysis_payload(mdposit_name)
    if data is None:
        return False
    write_analysis_result(experiment_id, simulation_path, mdposit_name, data)
    for variant_name in _summary_variant_names(data):
        variant_data = fetch_analysis_payload(variant_name)
        if variant_data is not None:
            write_analysis_result(experiment_id, simulation_path, variant_name, variant_data)
    return True


def complete_analysis_with_mdposit(
    job_name: str,
    experiment_id: str,
    simulation_path: str,
    analysis_name: str,
    delay_sec: float = 3.0,
) -> None:
    """
    Simulate an analysis job completing the way a real mwf run would.

    Sleeps `delay_sec` (the job's runtime), then materializes the result files
    from MDPosit; the job ends ERROR when the upstream has no such payload, as
    a real failure would.

    Shared by the k8s mock (_create_job lifecycle) and the seed's RUNNING
    analyses, so both finish with data instead of stalling.
    """
    time.sleep(delay_sec)
    try:
        if materialize_analysis(experiment_id, simulation_path, analysis_name):
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.FINISHED.value
            logger.debug("Analysis job %s completed with MDPosit data", job_name)
        else:
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.ERROR.value

    except Exception:
        logger.exception("Failed to fetch analysis '%s' for demo job %s", analysis_name, job_name)
        if job_name in demo_state.analysis_jobs:
            demo_state.analysis_jobs[job_name]["status"] = JobStatus.ERROR.value


def start_analysis_thread(
    job_name: str, experiment_id: str, simulation_path: str, analysis_name: str, delay_sec: float = 3.0
) -> None:
    """Schedule complete_analysis_with_mdposit on a daemon thread."""
    threading.Thread(
        target=complete_analysis_with_mdposit,
        args=(job_name, experiment_id, simulation_path, analysis_name, delay_sec),
        daemon=True,
    ).start()
