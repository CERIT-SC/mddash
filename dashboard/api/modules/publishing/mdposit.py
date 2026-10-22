"""MDPosit publication package: the manifest's files plus an MDDB `inputs.yaml` the user completes in VRE Lite."""

from http import HTTPStatus
from pathlib import Path

import yaml
from core.config import DATA_DIR, MDPOSIT_URL, MDPOSIT_VRE_LITE_URL
from core.enums import Engine
from core.errors import ApiError, BadRequest, InternalServerError
from core.utils import file_download_url

from modules.experiments.models import Experiment
from modules.simulations.manifest import Simulation, property_label


def prepare_package(experiment: Experiment, simulation_path: str) -> dict:
    """
    Prepare stateless MDPosit publication metadata from a simulation manifest (sync: file I/O only).

    Returns:
        Metadata file and selected file descriptors for MDPosit publishing.

    Raises:
        BadRequest: If MDPosit is unconfigured or required files are missing/invalid.
        InternalServerError: If metadata generation fails.
    """
    if not MDPOSIT_URL:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "MDPosit is not configured. Set MDPOSIT_URL to enable MDPosit publishing.",
            "urn:mddash:mdposit-not-configured",
            "MDPosit publishing isn't enabled on this deployment; contact the administrator.",
        )

    simulation = Simulation.get(experiment.id, simulation_path, experiment)
    simulation.require_files(["reference_structure", "run_input", "trajectory"])

    exp_dir = DATA_DIR / experiment.id
    if not exp_dir.exists():
        raise BadRequest("Experiment directory not found.")
    exp_dir_resolved = exp_dir.resolve()

    publish_roles = {
        "reference_structure": ("structure", {"pdb", "gro"}),
        "run_input": ("topology", {"top", "prmtop", "parm7", "psf", "tpr"}),
        "trajectory": ("trajectory", {"xtc", "trr", "nc", "dcd"}),
    }

    files: list[dict[str, str]] = []
    selected_paths: dict[str, Path] = {}

    for manifest_role, (publish_role, exts) in publish_roles.items():
        if manifest_role not in simulation.files:
            raise BadRequest(
                f"The simulation does not define a '{property_label(manifest_role)}' file, which MDPosit publishing requires."
            )

        file_path = simulation.resolve_role(manifest_role)
        if not file_path.is_file():
            raise BadRequest(f"The '{property_label(manifest_role)}' file does not exist.")

        extension = file_path.suffix.lstrip(".").lower()
        if extension not in exts:
            allowed = ", ".join(sorted(exts))
            raise BadRequest(
                f"The '{property_label(manifest_role)}' file has an unsupported extension '.{extension}'. Allowed: {allowed}."
            )

        relative_path = str(file_path.relative_to(exp_dir_resolved))
        selected_paths[publish_role] = file_path
        files.append({
            "role": publish_role,
            "path": relative_path,
            "url": file_download_url(experiment.id, relative_path),
        })

    metadata = _metadata(experiment, selected_paths)
    metadata_file = exp_dir / "inputs.yaml"
    metadata_relative_path = str(metadata_file.relative_to(exp_dir))

    try:
        metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    except OSError as exc:
        raise InternalServerError("Failed to generate metadata file.") from exc

    return {
        "metadata_file": {
            "path": metadata_relative_path,
            "url": file_download_url(experiment.id, metadata_relative_path),
        },
        "files": files,
        "vre_lite_url": MDPOSIT_VRE_LITE_URL or None,
    }


def _metadata(experiment: Experiment, selected_paths: dict[str, Path]) -> dict:
    """
    MDDB-compatible inputs.yaml metadata.

    Only fields we can determine without external assumptions are included.
    The user fills remaining fields in VRE Lite.
    """
    program = "GROMACS" if experiment.engine == Engine.GMX else "AMBER"
    return {
        "name": experiment.name,
        "program": program,
        "type": "trajectory",
        "method": "Classical MD",
        "input_structure_filepath": selected_paths["structure"].name,
        "input_topology_filepath": selected_paths["topology"].name,
        "input_trajectory_filepaths": [selected_paths["trajectory"].name],
    }
