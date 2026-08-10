"""MD engine tuning orchestration using Ray workers."""

import contextlib
import logging
import threading
from typing import Any

import ray
from ray.exceptions import RayError
from ray.util.state import get_task

from api.config import (
    EARLY_STOP_BASELINE_TRIALS,
    EARLY_STOP_BATCH_SIZE,
    RAY_ADDRESS,
    RUNTIME_WORKDIR,
    TRIAL_START_TIMEOUT_SECONDS,
)
from api.db.operations import (
    create_job,
    create_trial_result,
    get_job,
    update_job_sim_length,
    update_job_status,
    update_trial_result,
)
from api.engines.protocol import Engine, TrialConfig
from api.schemas.common import JobStatus, MDEngine

RAY_RUNTIME_ENV = {"working_dir": RUNTIME_WORKDIR}
# Ray State API is served by the head pod's dashboard agent (port 8265).
RAY_DASHBOARD_ADDRESS = f"http://{RAY_ADDRESS.removeprefix('ray://').split(':')[0]}:8265"
logger = logging.getLogger(__name__)

logger.info("Tuner module initialized")


class JobState:
    """Per-job state: background thread, cancellation event, and active Ray futures."""

    def __init__(self, thread: threading.Thread) -> None:
        """Store the job thread and initialise cancellation/futures tracking."""
        self.thread = thread
        self.cancelled = threading.Event()
        # Active Ray future -> DB trial ID, so any code path can map task state to trial.
        self.futures: dict[ray.ObjectRef, int] = {}


class JobContext:
    """Thread-safe registry of all in-flight tuning jobs."""

    def __init__(self) -> None:
        """Initialise an empty job registry with a reentrant lock."""
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def add_job(self, job_id: str, thread: threading.Thread) -> None:
        """Register a new job with its background thread."""
        with self._lock:
            self._jobs[job_id] = JobState(thread)

    def remove_job(self, job_id: str) -> None:
        """Remove a job from the registry (no-op if not present)."""
        with self._lock:
            self._jobs.pop(job_id, None)

    def is_cancelled(self, job_id: str) -> bool:
        """Return True if the job has been marked for cancellation."""
        with self._lock:
            state = self._jobs.get(job_id)
            return state is not None and state.cancelled.is_set()

    def mark_cancelled(self, job_id: str) -> threading.Event:
        """Set the cancellation flag for a job and return its event."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state:
                state.cancelled.set()
                return state.cancelled
            event = threading.Event()
            event.set()
            return event

    def add_futures(self, job_id: str, futures: dict[ray.ObjectRef, int]) -> None:
        """Register Ray futures belonging to a job for later cancellation and state lookup."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state:
                state.futures.update(futures)

    def remove_future(self, job_id: str, future: ray.ObjectRef) -> None:
        """Remove a completed future from the job's tracking set."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state:
                state.futures.pop(future, None)

    def get_futures(self, job_id: str) -> dict[ray.ObjectRef, int]:
        """Return a snapshot of all active futures for a job as future -> trial ID."""
        with self._lock:
            state = self._jobs.get(job_id)
            return dict(state.futures) if state else {}

    def is_thread_alive(self, job_id: str) -> bool:
        """Return True if the job's background thread is still running."""
        with self._lock:
            state = self._jobs.get(job_id)
            return state is not None and state.thread.is_alive()


_job_context = JobContext()

TrialConfigEntry = tuple[int, TrialConfig]


def _ensure_ray_initialized() -> None:
    if not ray.is_initialized():
        ray.init(address=RAY_ADDRESS, runtime_env=RAY_RUNTIME_ENV, ignore_reinit_error=True)
        logger.info("Connected to Ray cluster at %s", RAY_ADDRESS)


def _ray_task_state(future: ray.ObjectRef) -> str | None:
    """Return the Ray task state for a future, or None if unavailable (never raises)."""
    try:
        task = get_task(str(future.task_id()), address=RAY_DASHBOARD_ADDRESS)
    except Exception:
        logger.warning("Failed to query Ray task state for %s", future.task_id(), exc_info=True)
        return None
    return task.state if task else None


def _task_states(job_id: str) -> dict[int, str]:
    """Return trial ID -> Ray task state for all of the job's active futures."""
    states: dict[int, str] = {}
    for future, trial_id in _job_context.get_futures(job_id).items():
        if state := _ray_task_state(future):
            states[trial_id] = state
    return states


def trial_status_overrides(job_id: str) -> dict[int, JobStatus]:
    """Return submitted trials Ray reports as executing (RUNNING)."""
    return {
        trial_id: JobStatus.RUNNING for trial_id, state in _task_states(job_id).items() if state.startswith("RUNNING")
    }


def derive_job_status(db_status: JobStatus, trial_statuses: list[JobStatus]) -> JobStatus:
    """Derive the effective job status; terminal DB statuses always win."""
    if db_status in {JobStatus.FINISHED, JobStatus.ERROR}:
        return JobStatus(db_status)
    if any(s in {JobStatus.RUNNING, JobStatus.FINISHED, JobStatus.ERROR} for s in trial_statuses):
        return JobStatus.RUNNING
    return JobStatus.PENDING


@ray.remote(max_retries=3)
def _run_single_trial(
    job_id: str,
    trial_id: str,
    config: TrialConfig,
    engine: Engine,
    extra_args: str,
    nsteps: int = 25_000,
    best_steps_per_sec: float = 0.0,
) -> dict[str, Any]:
    """Execute a single trial on a Ray worker."""
    logger.info("Running trial %s: params=%s, nsteps=%d", trial_id, config.params, nsteps)
    result = engine.run_trial(config, trial_id, job_id, nsteps, extra_args, best_steps_per_sec)
    status = JobStatus.FINISHED if result.performance > 0 or result.early_stopped else JobStatus.ERROR
    logger.info(
        "Trial %s completed: status=%s, performance=%.2f ns/day, steps/sec=%.1f",
        trial_id,
        status,
        result.performance or 0.0,
        result.steps_per_sec,
    )
    return {
        "trial_id": trial_id,
        "status": status,
        "performance": result.performance,
        "steps_per_sec": result.steps_per_sec,
        "early_stopped": result.early_stopped,
    }


def _order_trial_configs(trial_configs: list[TrialConfigEntry]) -> list[TrialConfigEntry]:
    return sorted(trial_configs, key=lambda item: (-item[1].priority, -item[1].num_gpus, -item[1].num_cpus))


def _submit_trials(
    job_id: str,
    extra_args: str,
    trials: list[TrialConfigEntry],
    engine: Engine,
    nsteps: int,
    best_steps_per_sec: float,
) -> dict[ray.ObjectRef, int]:
    future_to_trial: dict[ray.ObjectRef, int] = {}
    for trial_id, cfg in trials:
        future = _run_single_trial.options(num_cpus=cfg.num_cpus, num_gpus=cfg.num_gpus).remote(
            job_id,
            str(trial_id),
            cfg,
            engine,
            extra_args,
            nsteps,  # ty: ignore[too-many-positional-arguments]  # Ray stub omits optional params.
            best_steps_per_sec,
        )
        future_to_trial[future] = trial_id
    # Trials stay PENDING until Ray reports RUNNING or the wait loop writes a terminal state.
    _job_context.add_futures(job_id, future_to_trial)
    return future_to_trial


def _fail_if_stalled(job_id: str, future_to_trial: dict[ray.ObjectRef, int], pending_futures: list) -> None:
    """
    Fail the batch if nothing began within the wait window.

    Executing trials mean progress (keep waiting); nothing executing means
    unschedulable — cancel the futures, ERROR the trials, and raise.
    """
    if any(state.startswith("RUNNING") for state in _task_states(job_id).values()):
        logger.info(
            "Job %s: no trial completed in %ds but trials are executing; continuing",
            job_id,
            TRIAL_START_TIMEOUT_SECONDS,
        )
        return
    remaining = [future_to_trial[f] for f in pending_futures]
    logger.warning(
        "Job %s: no trial began or completed in %ds; failing trials %s", job_id, TRIAL_START_TIMEOUT_SECONDS, remaining
    )
    for future in pending_futures:
        with contextlib.suppress(Exception):
            ray.cancel(future, force=False)
        update_trial_result(future_to_trial[future], JobStatus.ERROR, None)
        _job_context.remove_future(job_id, future)
    raise RuntimeError(
        f"No trial began or completed within {TRIAL_START_TIMEOUT_SECONDS}s; cluster busy or unavailable - retry later"
    )


def _process_trial_results(
    job_id: str,
    future_to_trial: dict[ray.ObjectRef, int],
    best_steps_per_sec: float,
) -> float:
    pending_futures = list(future_to_trial.keys())
    new_best = best_steps_per_sec

    while pending_futures:
        done, pending_futures = ray.wait(pending_futures, num_returns=1, timeout=TRIAL_START_TIMEOUT_SECONDS)
        if not done:
            _fail_if_stalled(job_id, future_to_trial, pending_futures)
            continue
        trial_id = future_to_trial[done[0]]
        try:
            res: dict[str, Any] = ray.get(done[0])
            if res:
                early_stopped = res.get("early_stopped", False)
                perf_value = None if early_stopped else res.get("performance")
                update_trial_result(trial_id, res.get("status", JobStatus.ERROR), perf_value)
                steps_per_sec = res.get("steps_per_sec", 0.0)
                if steps_per_sec > new_best and not early_stopped:
                    new_best = steps_per_sec
                    logger.info("Job %s: New best steps/sec: %.1f", job_id, new_best)
            else:
                logger.warning("Trial %d returned no result", trial_id)
                update_trial_result(trial_id, JobStatus.ERROR, None)
        except RayError as e:
            logger.warning("Trial %d failed: %s", trial_id, e)
            update_trial_result(trial_id, JobStatus.ERROR, None)
        finally:
            _job_context.remove_future(job_id, done[0])

    return new_best


def _run_tuning_async(
    job_id: str, engine: Engine, extra_args: str = "", nsteps: int = 25_000, nsteps_override: int | None = None
) -> None:
    pending_trial_ids: list[int] = []
    try:
        # Create trial records before connecting to Ray so GET returns them immediately.
        all_configs = engine.generate_configs()
        trial_configs = [(create_trial_result(job_id, cfg.params, JobStatus.PENDING, None), cfg) for cfg in all_configs]
        pending_trial_ids = [tid for tid, _ in trial_configs]
        trial_configs = _order_trial_configs(trial_configs)

        _ensure_ray_initialized()
        pending_trial_ids = []  # Ray is up; trials will be managed by the run loop from here
        update_job_status(job_id, JobStatus.RUNNING)

        # Full production simulation length for time/cost estimates; failure only degrades estimates.
        try:
            update_job_sim_length(job_id, engine.simulation_length_ns(job_id, nsteps_override))
        except Exception:
            logger.warning("Failed to extract simulation length for job %s", job_id, exc_info=True)

        best_steps_per_sec = 0.0

        baseline_count = min(EARLY_STOP_BASELINE_TRIALS, len(trial_configs))
        baseline_trials = trial_configs[:baseline_count]
        remaining_trials = trial_configs[baseline_count:]

        if baseline_trials:
            future_to_trial = _submit_trials(job_id, extra_args, baseline_trials, engine, nsteps, best_steps_per_sec)
            best_steps_per_sec = _process_trial_results(job_id, future_to_trial, best_steps_per_sec)

        batch_size = max(1, EARLY_STOP_BATCH_SIZE)
        for idx in range(0, len(remaining_trials), batch_size):
            if _job_context.is_cancelled(job_id):
                logger.info("Job %s cancelled, skipping remaining trials", job_id)
                break
            batch = remaining_trials[idx : idx + batch_size]
            future_to_trial = _submit_trials(job_id, extra_args, batch, engine, nsteps, best_steps_per_sec)
            best_steps_per_sec = _process_trial_results(job_id, future_to_trial, best_steps_per_sec)

        if _job_context.is_cancelled(job_id):
            logger.info("Job %s finished after cancellation; status already set", job_id)
        else:
            logger.info("All trials completed for job %s (best: %.1f steps/s)", job_id, best_steps_per_sec)
            if not _job_context.is_cancelled(job_id):
                update_job_status(job_id, JobStatus.FINISHED)
    except Exception:
        logger.exception("Tuning job %s failed", job_id)
        for trial_id in pending_trial_ids:
            update_trial_result(trial_id, JobStatus.ERROR, None)
        update_job_status(
            job_id, JobStatus.ERROR, "Tuning job failed. Please try again, or contact support if it persists."
        )
    finally:
        _job_context.remove_job(job_id)


def submit_tuning_job(
    job_id: str,
    engine: Engine,
    md_engine: MDEngine,
    extra_args: str = "",
    nsteps: int = 25_000,
    nsteps_override: int | None = None,
) -> str:
    """Submit a tuning job for any engine."""
    create_job(job_id, md_engine)
    thread = threading.Thread(
        target=_run_tuning_async, args=(job_id, engine, extra_args, nsteps, nsteps_override), daemon=True
    )
    _job_context.add_job(job_id, thread)
    thread.start()
    logger.info("Submitted tuning job %s (engine=%s)", job_id, md_engine.value)
    return job_id


def cancel_job(job_id: str) -> bool:
    """Cancel an in-flight job and its active Ray trials; returns False if job not found."""
    if not get_job(job_id):
        logger.warning("Cannot cancel: job %s not found", job_id)
        return False
    _job_context.mark_cancelled(job_id)
    futures_to_cancel = _job_context.get_futures(job_id)
    if futures_to_cancel:
        logger.info("Cancelling %d active trials for job %s", len(futures_to_cancel), job_id)
        for future in futures_to_cancel:
            try:
                ray.cancel(future, force=False)
            except Exception as e:
                logger.warning("Failed to cancel trial for job %s: %s", job_id, e)
    update_job_status(job_id, JobStatus.ERROR, "Cancelled by user")
    logger.info("Marked job %s as cancelled", job_id)
    return True


def sync_job_status(job_id: str) -> JobStatus | None:
    """Reconcile DB status with live thread/cancellation state; returns None if job not found."""
    job = get_job(job_id)
    if not job:
        return None
    if job.status in {JobStatus.FINISHED, JobStatus.ERROR}:
        return job.status
    if _job_context.is_cancelled(job_id):
        return JobStatus.ERROR
    if _job_context.is_thread_alive(job_id):
        return JobStatus.RUNNING
    if job.status == JobStatus.RUNNING:
        update_job_status(job_id, JobStatus.ERROR, "Job thread terminated unexpectedly")
        return JobStatus.ERROR
    if job.status == JobStatus.PENDING:
        update_job_status(job_id, JobStatus.ERROR, "Job failed to start - no active thread")
        return JobStatus.ERROR
    return job.status
