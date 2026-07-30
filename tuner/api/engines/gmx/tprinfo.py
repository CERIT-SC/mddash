"""Extract the full production simulation length from a GROMACS .tpr file."""

import logging
import re
import subprocess

import ray

logger = logging.getLogger(__name__)

_NSTEPS_RE = re.compile(r"^\s*nsteps\s*=\s*(\d+)", re.MULTILINE)
_DELTA_T_RE = re.compile(r"^\s*(?:delta[-_]t|dt)\s*=\s*([\d.eE+-]+)", re.MULTILINE)


def parse_dump_output(output: str) -> tuple[int, float] | None:
    """Parse (nsteps, delta_t) from `gmx dump -s` output. Returns None if either is missing."""
    nsteps_match = _NSTEPS_RE.search(output)
    delta_t_match = _DELTA_T_RE.search(output)
    if not nsteps_match or not delta_t_match:
        return None
    return int(nsteps_match.group(1)), float(delta_t_match.group(1))


def simulation_length_ns(tpr_path: str, nsteps_override: int | None = None) -> float | None:
    """
    Production simulation length (ns) of a .tpr file: nsteps * delta_t, from `gmx dump`.

    When nsteps_override is given (e.g. extra_args -nsteps for the production run),
    it replaces the step count stored in the .tpr; delta_t still comes from the dump.

    Dispatches to a Ray worker when a cluster is connected (GROMACS is only installed
    on worker images); falls back to a local attempt otherwise. Returns None on failure.
    """
    if ray.is_initialized():
        try:
            return ray.get(
                _simulation_length_ns_remote.remote(tpr_path, nsteps_override)  # ty: ignore[too-many-positional-arguments]
            )
        except Exception:
            logger.exception("Failed to extract simulation length from %s on a Ray worker", tpr_path)
            return None
    return _read_sim_length_ns(tpr_path, nsteps_override)


@ray.remote
def _simulation_length_ns_remote(tpr_path: str, nsteps_override: int | None = None) -> float | None:
    """Run `gmx dump` on a Ray worker where GROMACS is installed."""
    return _read_sim_length_ns(tpr_path, nsteps_override)


def _read_sim_length_ns(tpr_path: str, nsteps_override: int | None = None) -> float | None:
    """Read the simulation length via `gmx dump -s`; override wins over the .tpr's step count."""
    try:
        proc = subprocess.run(
            ["gmx", "dump", "-s", tpr_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("Could not run gmx dump for %s: %s", tpr_path, e)
        return None
    if proc.returncode != 0:
        logger.warning("gmx dump failed for %s (rc=%d): %s", tpr_path, proc.returncode, proc.stderr.strip())
        return None

    parsed = parse_dump_output(proc.stdout)
    if parsed is None:
        logger.warning("Could not parse nsteps/delta_t from gmx dump output for %s", tpr_path)
        return None
    nsteps, delta_t = parsed
    if nsteps_override is not None:
        nsteps = nsteps_override
    return nsteps * delta_t / 1000.0  # delta_t is in ps
