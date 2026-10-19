"""All jobs of an experiment (tuner, production runs, analyses) behind one facade."""

import asyncio
from collections.abc import Iterable
from typing import Annotated

from core.dependencies import ClientsDep, SessionDep
from fastapi import Depends

from modules.experiments.models import Experiment
from modules.jobs.analysis.models import AnalysisJob
from modules.jobs.analysis.service import AnalysisService
from modules.jobs.models import SimulationJob
from modules.jobs.runs import RunService
from modules.jobs.tuner.models import TunerJob
from modules.jobs.tuner.service import TunerService

type AnyJob = TunerJob | SimulationJob | AnalysisJob


class JobsService:
    """Refresh and teardown across every job type."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind the per-type job services to the request session."""
        self.tuner = TunerService(session, clients)
        self.runs: RunService[SimulationJob] = RunService(session, clients)
        self.analysis = AnalysisService(session, clients)

    async def refresh(self, experiment: Experiment) -> None:
        """Fetch the remote status of all tuner, simulation, and analysis jobs."""
        await asyncio.gather(
            *(self.tuner.refresh(job) for job in experiment.tuner_jobs),
            *(self.runs.refresh_status(job) for job in experiment.simulation_jobs),
            *(self.analysis.refresh_status(job) for job in experiment.analysis_jobs),
        )

    async def delete_remote(self, job: AnyJob) -> None:
        """Delete the job's upstream resources and files (the caller deletes the row)."""
        match job:
            case TunerJob():
                await self.tuner.delete_remote(job)
            case SimulationJob():
                await self.runs.delete_remote(job)
            case AnalysisJob():
                await self.analysis.delete_remote(job)

    @staticmethod
    def all_jobs(experiment: Experiment) -> Iterable[AnyJob]:
        """Every job row loaded on the experiment."""
        return (*experiment.tuner_jobs, *experiment.simulation_jobs, *experiment.analysis_jobs)

    @staticmethod
    def live_jobs(experiment: Experiment) -> list[AnyJob]:
        """Jobs that may still advance on their own (statuses must be refreshed)."""
        return [
            *(job for job in experiment.tuner_jobs if job.is_live),
            *(job for job in experiment.simulation_jobs if job.is_live),
            # AnalysisJob exposes only .status, no is_live shortcut.
            *(job for job in experiment.analysis_jobs if job.status.is_live),
        ]


JobsServiceDep = Annotated[JobsService, Depends()]
