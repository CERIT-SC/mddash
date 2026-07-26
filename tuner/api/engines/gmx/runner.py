"""GROMACS mdrun execution with early stopping support."""

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

from api.config import (
    EARLY_STOP_CHECK_INTERVAL,
    EARLY_STOP_ENABLED,
    EARLY_STOP_THRESHOLD,
    EARLY_STOP_WARMUP_SECONDS,
    EARLY_STOP_WARMUP_STEPS,
    JOBS_DIR,
    TPR_DIR,
)
from api.engines.gmx.config import GmxTrialConfig, PMEMode
from api.utils import tail

logger = logging.getLogger(__name__)


def run_mdrun(
    config: GmxTrialConfig,
    trial_id: str,
    job_id: str,
    extra_args: str = "",
    nsteps: int = 25_000,
    best_steps_per_sec: float = 0.0,
) -> tuple[float, float, bool]:
    """
    Execute GROMACS mdrun with the given config and return performance.

    Args:
        config: Trial configuration
        trial_id: Unique trial identifier
        job_id: Parent job identifier
        extra_args: Additional mdrun arguments
        nsteps: Number of steps to run
        best_steps_per_sec: Best steps/sec observed so far (for early stopping)

    Returns:
        Tuple of (performance_ns_day, steps_per_sec, early_stopped).
        Returns (0.0, 0.0, False) on failure.
    """
    tpr_path = str(TPR_DIR / f"{job_id}_md.tpr")
    trial_dir = JOBS_DIR / job_id / trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(config.ntomp)

    cmd = _build_command(config, tpr_path, nsteps)
    if extra_args:
        cmd += shlex.split(extra_args)

    stdout_log = trial_dir / "stdout.log"
    stderr_log = trial_dir / "stderr.log"

    result = _run_command_with_monitoring(
        cmd, stdout_log, stderr_log, env, trial_dir, f"Trial {trial_id}", best_steps_per_sec
    )
    if result is None:
        return 0.0, 0.0, False

    early_stopped, final_steps_per_sec = result
    if early_stopped:
        logger.info(
            "Trial %s early stopped (%.1f steps/s vs best %.1f)", trial_id, final_steps_per_sec, best_steps_per_sec
        )
        return 0.0, final_steps_per_sec, True

    performance = _parse_performance(stdout_log, stderr_log)
    return performance, final_steps_per_sec, False


def _build_command(config: GmxTrialConfig, tpr_path: str, nsteps: int = 25_000) -> list[str]:
    """Build the mpirun + gmx mdrun command."""
    cmd = [
        "mpirun",
        "-np",
        str(config.np),
        "gmx",
        "mdrun",
        "-v",  # Verbose output for "live" progress monitoring
        "-ntomp",
        str(config.ntomp),
        "-nb",
        config.nb,
        "-pme",
        config.pme,
        "-s",
        tpr_path,
        "-nsteps",
        str(nsteps),
        "-cpt",
        "-1",  # Disable checkpointing for tuning
    ]

    if config.pme == PMEMode.CPU and config.np > 1:
        cmd += ["-npme", "1"]

    return cmd


def _parse_performance(stdout_log: Path, stderr_log: Path) -> float:
    """Parse performance (ns/day) from GROMACS output."""
    output = tail(stdout_log, n=50) + tail(stderr_log, n=50)
    match = re.search(r"Performance:\s+(\d+\.?\d*)", output)
    return float(match.group(1)) if match else 0.0


def _parse_progress(stderr_log: Path) -> int | None:
    """
    Parse current step number from GROMACS verbose output.

    The -v flag produces lines like:
        step 20800, will finish Tue Feb  3 09:17:22 2026
        step 21100, remaining wall clock time:   299 s
    """
    try:
        output = tail(stderr_log, n=30)
        # Find the last step number in the output
        matches = re.findall(r"step\s+(\d+),", output, re.IGNORECASE)
        if matches:
            return int(matches[-1])
    except (OSError, ValueError):
        pass
    return None


def _run_command_with_monitoring(
    cmd: list[str],
    stdout_log: Path,
    stderr_log: Path,
    env: dict[str, str],
    cwd: Path,
    context: str,
    best_steps_per_sec: float,
) -> tuple[bool, float] | None:
    """
    Run a subprocess with progress monitoring and early stopping.

    Args:
        cmd: Command to execute
        stdout_log: Path for stdout redirection
        stderr_log: Path for stderr redirection
        env: Environment variables
        cwd: Working directory
        context: Description for logging
        best_steps_per_sec: Best steps/sec observed (for early stopping comparison)

    Returns:
        Tuple of (early_stopped, final_steps_per_sec) on success, None on failure.
    """
    try:
        with stdout_log.open("w", encoding="utf-8") as out, stderr_log.open("w", encoding="utf-8") as err:
            process = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=err,
                text=True,
                env=env,
                cwd=cwd,
                start_new_session=True,  # Create new session for clean termination
            )
            try:
                return _monitor_process(process, stderr_log, context, best_steps_per_sec)
            finally:
                _stop_process_group(process)

    except OSError as e:
        if e.errno == errno.ESTALE:
            logger.info("%s logs removed while job was deleted; skipping error", context)
        else:
            logger.exception("%s failed", context)
    except Exception:
        logger.exception("%s failed", context)

    return None


def _terminate_process_group(process: subprocess.Popen, sig: int) -> None:
    """Safely terminate a process group."""
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


def _should_early_stop(current_step: int, elapsed_time: float, steps_per_sec: float, best_steps_per_sec: float) -> bool:
    """Determine if early stopping criteria are met."""
    if best_steps_per_sec <= 0:
        return False

    # Kick in if we've reached step threshold OR if we've been running long enough to have a stable reading
    warmup_reached = (current_step >= EARLY_STOP_WARMUP_STEPS) or (elapsed_time >= EARLY_STOP_WARMUP_SECONDS)

    return EARLY_STOP_ENABLED and warmup_reached and steps_per_sec < best_steps_per_sec * EARLY_STOP_THRESHOLD


def _monitor_process(
    process: subprocess.Popen,
    stderr_log: Path,
    context: str,
    best_steps_per_sec: float,
) -> tuple[bool, float] | None:
    """Monitor process execution and apply early stopping if needed."""
    start_time = time.time()
    last_step = 0
    steps_per_sec = 0.0
    early_stopped = False

    while process.poll() is None:
        time.sleep(EARLY_STOP_CHECK_INTERVAL)

        current_step = _parse_progress(stderr_log)
        if current_step is None:
            continue

        elapsed = time.time() - start_time
        if elapsed > 0:
            steps_per_sec = current_step / elapsed

        if _should_early_stop(current_step, elapsed, steps_per_sec, best_steps_per_sec):
            logger.info(
                "%s: early stopping at step %d (%.1f steps/s < %.1f threshold)",
                context,
                current_step,
                steps_per_sec,
                best_steps_per_sec * EARLY_STOP_THRESHOLD,
            )
            _terminate_process_group(process, signal.SIGTERM)
            early_stopped = True
            break

        last_step = current_step

    # Wait for process to finish (either naturally or after SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        logger.warning("%s: process did not terminate after SIGTERM, sending SIGKILL", context)
        _terminate_process_group(process, signal.SIGKILL)
        process.wait()

    # Calculate final steps/sec if we haven't already
    if not early_stopped and last_step > 0:
        final_step = _parse_progress(stderr_log) or last_step
        elapsed = time.time() - start_time
        if elapsed > 0:
            steps_per_sec = final_step / elapsed

    if not early_stopped and process.returncode != 0:
        logger.error("%s failed with code %d", context, process.returncode)
        if stderr_log.exists():
            logger.error("GROMACS stderr:\n%s", tail(stderr_log, n=20))
        return None

    return early_stopped, steps_per_sec
