"""AMBER pmemd execution with early stopping support."""

import contextlib
import errno
import logging
import os
import re
import shlex
import signal
import subprocess
import time
from pathlib import Path

from api.config import EARLY_STOP_CHECK_INTERVAL, EARLY_STOP_COST_RATIO, INPUTS_DIR, JOBS_DIR
from api.engines.amber.config import AmberBinary, AmberTrialConfig
from api.engines.amber.mdin import patch_mdin_for_benchmark
from api.engines.early_stop import _should_early_stop
from api.utils import tail

logger = logging.getLogger(__name__)


def run_pmemd(
    config: AmberTrialConfig,
    trial_id: str,
    job_id: str,
    extra_args: str = "",
    nsteps: int = 25_000,
    best_steps_per_sec: float = 0.0,
    best_cost_per_step: float = 0.0,
) -> tuple[float, float, bool]:
    """
    Execute pmemd with the given config and return (performance_ns_day, steps_per_sec, early_stopped).

    Returns (0.0, 0.0, False) on failure.
    """
    trial_dir = JOBS_DIR / job_id / trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)

    prmtop = str(INPUTS_DIR / f"{job_id}_md.prmtop")
    inpcrd = str(INPUTS_DIR / f"{job_id}_md.inpcrd")
    mdin_source = INPUTS_DIR / f"{job_id}_md.mdin"

    patched_mdin = trial_dir / "mdin"
    try:
        patched_mdin.write_text(patch_mdin_for_benchmark(mdin_source.read_text(), nsteps, config.ewald))
    except Exception:
        logger.exception("Trial %s (job %s): failed to prepare mdin input", trial_id, job_id)
        return 0.0, 0.0, False

    mdout = trial_dir / "mdout"
    mdinfo = trial_dir / "mdinfo"
    restart = trial_dir / "restart.rst7"
    traj = trial_dir / "traj.nc"

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(config.ntomp)  # CUDA ntomp is always 1; set unconditionally for predictability

    cmd = _build_command(config, str(patched_mdin), prmtop, inpcrd, str(mdout), str(mdinfo), str(restart), str(traj))
    if extra_args:
        cmd += shlex.split(extra_args)

    result = _run_command_with_monitoring(
        cmd,
        mdout,
        mdinfo,
        trial_dir,
        f"Trial {trial_id}",
        best_steps_per_sec,
        env,
        config.footprint.hourly_cost(),
        best_cost_per_step,
    )
    if result is None:
        return 0.0, 0.0, False

    early_stopped, final_steps_per_sec = result
    if early_stopped:
        logger.info(
            "Trial %s early stopped (%.1f steps/s vs best %.1f)",
            trial_id,
            final_steps_per_sec,
            best_steps_per_sec,
        )
        return 0.0, final_steps_per_sec, True

    performance = _parse_amber_performance(tail(mdout, n=50))
    return performance, final_steps_per_sec, False


def _build_command(
    config: AmberTrialConfig,
    mdin: str,
    prmtop: str,
    inpcrd: str,
    mdout: str,
    mdinfo: str,
    restart: str,
    traj: str,
) -> list[str]:
    base = [
        config.binary.value,
        "-O",
        "-i",
        mdin,
        "-p",
        prmtop,
        "-c",
        inpcrd,
        "-o",
        mdout,
        "-inf",
        mdinfo,
        "-r",
        restart,
        "-x",
        traj,
    ]
    if config.binary == AmberBinary.PMEMD_MPI:
        return ["mpirun", "-np", str(config.np), *base]
    return base


def _parse_amber_performance(content: str) -> float:
    """Parse ns/day from mdout — last occurrence is the 'all steps' summary."""
    matches = re.findall(r"ns/day\s*=\s*([\d.]+)", content)
    return float(matches[-1]) if matches else 0.0


def _parse_amber_progress(content: str) -> int | None:
    """Parse current step number from mdinfo content."""
    match = re.search(r"Nstep\s*=\s*(\d+)", content)
    if match:
        return int(match.group(1))
    return None


def _run_command_with_monitoring(
    cmd: list[str],
    _mdout: Path,
    mdinfo: Path,
    cwd: Path,
    context: str,
    best_steps_per_sec: float,
    env: dict[str, str],
    hourly_cost: float,
    best_cost_per_step: float,
) -> tuple[bool, float] | None:
    stdout_path = cwd / "stdout.log"
    stderr_path = cwd / "stderr.log"
    try:
        with (
            stdout_path.open("w") as stdout_file,
            stderr_path.open("w") as stderr_file,
            subprocess.Popen(
                cmd,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                cwd=cwd,
                start_new_session=True,
                env=env,
            ) as process,
        ):
            try:
                result = _monitor_process(process, mdinfo, context, best_steps_per_sec, hourly_cost, best_cost_per_step)
            finally:
                _stop_process_group(process)
        if result is None:
            for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
                content = path.read_text().strip()
                if content:
                    logger.error("%s %s:\n%s", context, label, content)
        return result
    except OSError as e:
        if e.errno == errno.ESTALE:
            logger.info("%s logs removed while job was deleted; skipping error", context)
        else:
            logger.exception("%s failed", context)
    except Exception:
        logger.exception("%s failed", context)
    return None


def _terminate_process_group(process: subprocess.Popen, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, OSError):
        os.killpg(os.getpgid(process.pid), sig)


def _stop_process_group(process: subprocess.Popen) -> None:
    """Stop native child processes when monitoring is interrupted."""
    if process.poll() is not None:
        return
    _terminate_process_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process, signal.SIGKILL)
        process.wait()


def _monitor_process(
    process: subprocess.Popen,
    mdinfo: Path,
    context: str,
    best_steps_per_sec: float,
    hourly_cost: float,
    best_cost_per_step: float,
) -> tuple[bool, float] | None:
    start_time = time.time()
    last_step = 0
    steps_per_sec = 0.0
    early_stopped = False

    while process.poll() is None:
        time.sleep(EARLY_STOP_CHECK_INTERVAL)

        content = tail(mdinfo, n=20) if mdinfo.exists() else ""
        current_step = _parse_amber_progress(content)
        if current_step is None:
            continue

        elapsed = time.time() - start_time
        if elapsed > 0:
            steps_per_sec = current_step / elapsed

        cost_per_step = hourly_cost / steps_per_sec if steps_per_sec > 0 else float("inf")
        if _should_early_stop(
            current_step, elapsed, steps_per_sec, best_steps_per_sec, cost_per_step, best_cost_per_step
        ):
            logger.info(
                "%s: early stopping at step %d (%.1f steps/s too slow, cost/step %.4f > %.4f)",
                context,
                current_step,
                steps_per_sec,
                cost_per_step,
                best_cost_per_step * EARLY_STOP_COST_RATIO,
            )
            _terminate_process_group(process, signal.SIGTERM)
            early_stopped = True
            break

        last_step = current_step

    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        logger.warning("%s: process did not terminate after SIGTERM, sending SIGKILL", context)
        _terminate_process_group(process, signal.SIGKILL)
        process.wait()

    if not early_stopped:
        content = tail(mdinfo, n=20) if mdinfo.exists() else ""
        final_step = _parse_amber_progress(content) or last_step
        if final_step > 0:
            elapsed = time.time() - start_time
            if elapsed > 0:
                steps_per_sec = final_step / elapsed

    if not early_stopped and process.returncode != 0:
        logger.error("%s failed with code %d", context, process.returncode)
        return None

    return early_stopped, steps_per_sec
