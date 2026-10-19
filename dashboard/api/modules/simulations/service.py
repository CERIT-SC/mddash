"""Simulation manifests with their job-derived state (lock, step, live)."""

from typing import Annotated

import anyio
from core.dependencies import ClientsDep, SessionDep
from fastapi import Depends

from modules.experiments.models import Experiment
from modules.jobs.service import JobsService
from modules.simulations.manifest import Simulation, experiment_jobs


class SimulationService:
    """
    Manifest reads and writes; serialized dicts read the experiment's jobs, so those are refreshed first.

    Manifest and file work runs in a worker thread; values the job properties cache are committed after.
    """

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session and the job services."""
        self._session = session
        self._jobs = JobsService(session, clients)

    async def list_simulations(self, experiment: Experiment) -> list[dict]:
        """All simulations of an experiment (invalid and unreadable ones included)."""
        await self._jobs.refresh(experiment)
        result = await anyio.to_thread.run_sync(
            lambda: [s.to_dict() for s in Simulation.list(experiment.id, experiment)]
        )
        await self._session.commit()
        return result

    async def get(self, experiment: Experiment, simulation_path: str) -> dict:
        """One simulation by its experiment-relative path."""
        await self._jobs.refresh(experiment)
        result = await anyio.to_thread.run_sync(
            lambda: Simulation.get(experiment.id, simulation_path, experiment).to_dict()
        )
        await self._session.commit()
        return result

    async def create(self, experiment: Experiment, payload: dict) -> dict:
        """Write a new manifest."""
        await self._jobs.refresh(experiment)
        result = await anyio.to_thread.run_sync(lambda: Simulation.write(experiment, payload).to_dict())
        await self._session.commit()
        return result

    async def update(self, experiment: Experiment, simulation_path: str, payload: dict) -> dict:
        """Edit an unlocked manifest."""
        await self._jobs.refresh(experiment)
        result = await anyio.to_thread.run_sync(
            lambda: Simulation.update(experiment, simulation_path, payload).to_dict()
        )
        await self._session.commit()
        return result

    async def delete(self, experiment: Experiment, simulation_path: str) -> None:
        """
        Delete a manifest and cascade-delete its jobs.

        Removes the tuner, run, and analysis rows (and their upstream resources), then
        the manifest file. Data files are left untouched.
        """
        simulation_path = await anyio.to_thread.run_sync(Simulation.existing_path, experiment.id, simulation_path)
        jobs = experiment_jobs(experiment, simulation_path)
        for job in (*jobs.tuner, *jobs.simulation, *jobs.analysis):
            await self._jobs.delete_remote(job)
            await self._session.delete(job)
        await self._session.commit()
        await anyio.to_thread.run_sync(Simulation.remove_file, experiment.id, simulation_path)


SimulationServiceDep = Annotated[SimulationService, Depends()]
