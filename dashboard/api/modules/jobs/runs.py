"""Production run lifecycle shared by the MDRun engines (GROMACS, AMBER)."""

import logging
from collections.abc import Sequence
from typing import ClassVar, cast

import anyio
from core.cache import simulation_status_cache
from core.concurrency import gather
from core.dependencies import ClientsDep, SessionDep
from core.enums import JobStatus
from core.errors import BadRequest, Conflict, NotFound
from sqlalchemy.exc import IntegrityError

from modules.jobs.models import SimulationJob
from modules.jobs.status import refresh_recorded
from modules.simulations.manifest import Simulation

logger = logging.getLogger(__name__)

ACTIVE_RUN_CONFLICT = "A run is already active for this simulation; stop it first to submit a new run."


class RunService[J: SimulationJob]:
    """
    One run row per simulation, mirrored from MDRun.

    The base class serves any engine (`SimulationJob` rows of the experiment);
    engine services narrow `model` and add submission.
    """

    model: ClassVar[type[SimulationJob]] = SimulationJob
    label: ClassVar[str] = "Simulation"

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session and the MDRun client."""
        self._session = session
        self._mdrun = clients.mdrun

    async def refresh_status(self, job: SimulationJob) -> JobStatus:
        """Fetch the MDRun status (short TTL cache); terminal states never change, so they skip the fetch."""

        async def fetch() -> JobStatus:
            return JobStatus.from_string((await self._mdrun.get_job(job.MDRUN_ENGINE, job.id))["status"])

        await refresh_recorded(job, job.id, simulation_status_cache, fetch)
        return job.status

    async def list_jobs(self, experiment_id: str) -> Sequence[J]:
        """List the experiment's runs of this engine, status refreshed."""
        stmt = self.model.query().filter_by(experiment_id=experiment_id)
        jobs = cast("Sequence[J]", (await self._session.execute(stmt)).scalars().all())
        await gather(*(self.refresh_status(job) for job in jobs))
        return jobs

    async def find(self, experiment_id: str, simulation_path: str) -> J | None:
        """Find the simulation's single run row (unique per experiment and path), or None."""
        stmt = self.model.query().filter_by(experiment_id=experiment_id, simulation_path=simulation_path)
        return cast("J | None", (await self._session.execute(stmt)).scalars().first())

    async def get(self, experiment_id: str, simulation_path: str, *, refresh: bool = True) -> J:
        """
        Get the simulation's run row (status refreshed unless `refresh` is False).

        Raises:
            NotFound: If the simulation never ran.
        """
        job = await self.find(experiment_id, simulation_path)
        if job is None:
            raise NotFound(f"{self.label} job for simulation {simulation_path} in experiment {experiment_id} not found")
        if refresh:
            await self.refresh_status(job)
        return job

    async def delete_remote(self, job: SimulationJob) -> None:
        """Delete the MDRun job and this run's result files (the caller deletes the row)."""
        await self._mdrun.delete_job(job.MDRUN_ENGINE, job.id)
        await anyio.to_thread.run_sync(job.cleanup_files)

    async def remove(self, experiment_id: str, simulation_path: str) -> J | None:
        """
        Delete the simulation's run: its MDRun job, DB row, and result files.

        Returns:
            The deleted row, or None when the simulation never ran.
        """
        job = await self.find(experiment_id, simulation_path)
        if job is None:
            return None
        await self.delete_remote(job)
        await self._session.delete(job)
        await self._session.commit()
        return job

    async def delete(self, experiment_id: str, simulation_path: str) -> None:
        """
        Delete the simulation's run.

        Raises:
            NotFound: If the simulation never ran.
        """
        if not await self.remove(experiment_id, simulation_path):
            raise NotFound(f"{self.label} job for simulation {simulation_path} in experiment {experiment_id} not found")

    async def stop(self, experiment_id: str, simulation_path: str) -> None:
        """
        Stop the run gracefully, keeping all data and the row (it later extends, GMX, or analyzes as-is).

        The outcome is re-read after the stop: a run that finishes first stays FINISHED, not STOPPED.

        Raises:
            BadRequest: If the run is not live.
        """
        job = await self.get(experiment_id, simulation_path)
        if not job.is_live:
            raise BadRequest("Only a live run can be stopped.")
        await self._mdrun.stop_job(job.MDRUN_ENGINE, job.id)
        try:
            status = JobStatus.from_string((await self._mdrun.get_job(job.MDRUN_ENGINE, job.id))["status"])
        except Exception:
            logger.exception(f"Could not re-read status of job {job.id} after stop; assuming STOPPED")
            status = JobStatus.STOPPED
        job.mark_status(status)
        simulation_status_cache.pop(job.id, None)
        await self._session.commit()

    async def replace_terminal_run(self, experiment_id: str, simulation_path: str) -> None:
        """
        Clear the way for a new run: a terminal run (finished, stopped, or failed) is deleted.

        Raises:
            Conflict: If a live run already exists for this simulation.
        """
        prior = await self.find(experiment_id, simulation_path)
        if prior is None:
            return
        await self.refresh_status(prior)
        if prior.is_live:
            raise Conflict(ACTIVE_RUN_CONFLICT)
        await self.remove(experiment_id, simulation_path)

    async def commit_new_run(self, job: J, simulation: Simulation) -> J:
        """
        Persist a just-submitted run and lock its manifest.

        Raises:
            Conflict: If another request committed a run for this simulation first (its MDRun job is torn down).
        """
        self._session.add(job)
        await anyio.to_thread.run_sync(job.cleanup_files)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            await self._mdrun.delete_job(job.MDRUN_ENGINE, job.id)
            raise Conflict(ACTIVE_RUN_CONFLICT) from None
        simulation.mark_readonly()
        await self.refresh_status(job)
        return job
