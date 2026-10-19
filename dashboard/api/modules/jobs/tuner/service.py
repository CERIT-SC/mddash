"""Tuner jobs: submission, status mirroring, stop (trials preserved), and trial logs."""

import asyncio
import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Annotated

import httpx
from core.cache import tuner_last_known_status, tuner_status_cache
from core.dependencies import ClientsDep, SessionDep
from core.enums import Engine, JobStatus
from core.errors import ApiError, NotFound
from fastapi import Depends

from modules.experiments.dependencies import get_experiment_or_404
from modules.jobs.tuner.models import TunerJob
from modules.simulations.manifest import Simulation

logger = logging.getLogger(__name__)

# TODO: drop after user testing (#166). Pins the tuner's length estimate to the forced 500k GROMACS run.
FORCED_GMX_NSTEPS = 500000


def _engine(job_or_engine: TunerJob | Engine) -> str:
    """Tuner API path segment of the job's engine."""
    engine = job_or_engine.engine if isinstance(job_or_engine, TunerJob) else job_or_engine
    return engine.value.lower()


class TunerService:
    """One tuning job per simulation manifest."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session and the tuner client."""
        self._session = session
        self._tuner = clients.tuner

    async def refresh(self, job: TunerJob) -> None:
        """
        Fetch the tuner status (short TTL cache), falling back to the last known status on errors.

        A FINISHED job is stopped (trials persisted, tuner freed); so is one the tuner no longer knows (404).
        """
        if job.is_stopped:
            return

        if (cached := tuner_status_cache.get(job.id)) is not None:
            job.record_status(cached)
            return

        job.record_status(tuner_last_known_status.get(job.id, {}))
        try:
            status = await self._tuner.poll_status(_engine(job), job.id)

            if status.get("status") == JobStatus.ERROR and not job.error_message:
                job.error_message = status.get("error") or "Tuning job failed on the tuner."

            if "status" not in status or "trials" not in status:
                raise ValueError(f"Incomplete status response from tuner for job {job.id}")

            tuner_status_cache[job.id] = status
            tuner_last_known_status[job.id] = status
            job.record_status(status)

            # A finished job never changes again: persist trials and free the tuner.
            if status["status"] == JobStatus.FINISHED:
                await self.stop(job)

        except TimeoutError:
            logger.warning(f"Timeout fetching tuner status for job {job.id}")
        except httpx.HTTPStatusError as exc:
            # 404 means the tuner no longer has this job (reaped or restarted); stop re-polling.
            if exc.response.status_code == HTTPStatus.NOT_FOUND:
                logger.warning(f"Tuner job {job.id} not found on tuner; stopping")
                await self.stop(job)
            else:
                logger.exception(f"Error fetching tuner status for job {job.id}")
        except Exception:
            logger.exception(f"Error fetching tuner status for job {job.id}")

    async def list_jobs(self, experiment_id: str) -> Sequence[TunerJob]:
        """List the experiment's tuner jobs, refreshed."""
        jobs = (await self._session.execute(TunerJob.query().filter_by(experiment_id=experiment_id))).scalars().all()
        await asyncio.gather(*(self.refresh(job) for job in jobs))
        return jobs

    async def find(self, experiment_id: str, simulation_path: str) -> TunerJob | None:
        """Find the simulation's tuner job, or None."""
        stmt = TunerJob.query().filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
        return (await self._session.execute(stmt)).scalars().first()

    async def get(self, experiment_id: str, simulation_path: str, *, refresh: bool = False) -> TunerJob:
        """
        Get the simulation's tuner job.

        Raises:
            NotFound: If the simulation was never tuned.
        """
        job = await self.find(experiment_id, simulation_path)
        if job is None:
            raise NotFound(f"Tuner job for {simulation_path} not found")
        if refresh:
            await self.refresh(job)
        return job

    async def start(self, experiment_id: str, simulation_path: str, nsteps: int) -> tuple[TunerJob, bool]:
        """
        Start a tuner job for a simulation manifest; an existing healthy job is returned instead.

        Launch files and ``extra_args`` are derived from the manifest and passed
        to the tuner; they are not persisted in the dashboard DB.

        Returns:
            The (refreshed) job and whether it was created by this call.

        Raises:
            ApiError: If the tuner is unavailable (upstream-unavailable).
        """
        experiment = await get_experiment_or_404(self._session, experiment_id)

        existing = await self.find(experiment_id, simulation_path)
        if existing:
            if not existing.error_message:
                await self.refresh(existing)
                return existing, False
            await self.delete_remote(existing)
            await self._session.delete(existing)
            await self._session.commit()

        simulation = Simulation.get(experiment.id, simulation_path, experiment)
        simulation.require_files(
            ["run_input"] if experiment.engine == Engine.GMX else ["topology", "coordinates", "control"]
        )
        extra_args = simulation.extra_args
        if experiment.engine == Engine.GMX:
            extra_args = f"{extra_args} -nsteps {FORCED_GMX_NSTEPS}".strip()

        files = (
            {"file": simulation.resolve_role("run_input")}
            if experiment.engine == Engine.GMX
            else {
                "prmtop": simulation.resolve_role("topology"),
                "inpcrd": simulation.resolve_role("coordinates"),
                "mdin": simulation.resolve_role("control"),
            }
        )
        try:
            response = await self._tuner.submit(_engine(experiment.engine), files, nsteps=nsteps, extra_args=extra_args)
        except httpx.HTTPError as exc:
            logger.error("Tuner submit failed for experiment %s: %s", experiment.id, exc)
            raise ApiError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Failed to submit tuning job.",
                "urn:mddash:upstream-unavailable",
                "The tuning service is unavailable; try again in a moment.",
            ) from exc

        job = TunerJob(
            id=response["id"],
            experiment_id=experiment.id,
            experiment=experiment,
            simulation_path=simulation_path,
            nsteps=nsteps,
        )
        self._session.add(job)
        await self._session.commit()

        simulation.mark_readonly()

        logger.info(
            f"Tuner job {response['id']} started for experiment {experiment.id} "
            f"with engine {experiment.engine} (simulation {simulation_path})"
        )
        await self.refresh(job)
        return job, True

    async def _delete_on_tuner(self, job: TunerJob) -> None:
        try:
            await self._tuner.delete_job(_engine(job), job.id)
        except httpx.HTTPError:
            logger.exception(f"Failed to delete tuner job {job.id}")

    async def stop(self, job: TunerJob) -> None:
        """Stop the tuner job and preserve observed trials (the caller commits)."""
        if job.is_stopped:
            return
        job.preserve_trials(tuner_last_known_status.get(job.id, {}))
        await self._delete_on_tuner(job)
        tuner_status_cache.clear()
        logger.info(f"Stopped tuner job {job.id}")

    async def stop_by_path(self, experiment_id: str, simulation_path: str) -> None:
        """Stop the simulation's tuner job, keeping its observed trials."""
        await self.stop(await self.get(experiment_id, simulation_path))
        await self._session.commit()

    async def delete_remote(self, job: TunerJob) -> None:
        """Delete the job on the tuner; a stopped job is already gone there (the caller deletes the row)."""
        if job.is_stopped:
            return
        await self._delete_on_tuner(job)

    async def delete(self, experiment_id: str, simulation_path: str) -> None:
        """Delete the simulation's tuner job and its tuner-side resources."""
        job = await self.get(experiment_id, simulation_path)
        await self.delete_remote(job)
        await self._session.delete(job)
        await self._session.commit()

    async def trial_log(self, experiment_id: str, simulation_path: str, trial_id: str, stream: str) -> str:
        """`stdout` or `stderr` of a tuning trial."""
        job = await self.get(experiment_id, simulation_path)
        return await self._tuner.trial_log(_engine(job), job.id, trial_id, stream)


TunerServiceDep = Annotated[TunerService, Depends()]
