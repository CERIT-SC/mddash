"""Analysis K8s Jobs: submission (one analysis set per simulation), status, logs, and cleanup."""

import logging
import uuid
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Annotated

import anyio
from clients.k8s import parse_cpu, parse_memory
from core.cache import analysis_status_cache
from core.concurrency import gather
from core.config import ANALYSIS_IMAGE, ANALYSIS_RESOURCES
from core.dependencies import ClientsDep, SessionDep
from core.enums import AnalysisType, Engine, JobStatus, PreprocessingMode
from core.errors import BadRequest, Forbidden, NotFound
from fastapi import Depends

from modules.experiments.models import Experiment
from modules.jobs.analysis.command import format_mwf_analysis_command
from modules.jobs.analysis.models import AnalysisJob
from modules.jobs.runs import RunService
from modules.jobs.status import refresh_recorded
from modules.simulations.manifest import Simulation

logger = logging.getLogger(__name__)

# The MDDB workflow prints container setup noise before this line.
_WORKFLOW_START_MARKER = "Running MDDB workflow"


def analysis_inputs(
    experiment: Experiment, simulation_path: str, preprocessing_mode: PreprocessingMode
) -> tuple[Path, Path | None, Path | None]:
    """Resolve (trajectory, structure, topology) for an analysis; sync (manifest and file checks)."""
    simulation = Simulation.get(experiment.id, simulation_path, experiment)
    simulation.require_files(["trajectory"])
    trajectory_path = simulation.resolve_role("trajectory")
    if not trajectory_path.is_file():
        raise BadRequest(f"Trajectory file {trajectory_path} does not exist.")

    topology_path: Path | None = None
    if experiment.engine == Engine.GMX and "run_input" in simulation.files:
        topology_path = simulation.resolve_role("run_input")
    elif "topology" in simulation.files:
        topology_path = simulation.resolve_role("topology")

    structure_path: Path | None = None
    if "reference_structure" in simulation.files:
        structure_path = simulation.resolve_role("reference_structure")

    if preprocessing_mode in {PreprocessingMode.IMAGE, PreprocessingMode.IMAGE_FIT} and (
        not topology_path or topology_path.suffix.lower() != ".tpr"
    ):
        raise BadRequest("Trajectory preprocessing requires a simulation TPR file (.tpr).")

    if experiment.engine == Engine.GMX and preprocessing_mode is PreprocessingMode.AS_IS and structure_path is not None:
        topology_path = None
    return trajectory_path, structure_path, topology_path


class AnalysisService:
    """On-demand mwf analyses of simulation trajectories."""

    def __init__(self, session: SessionDep, clients: ClientsDep) -> None:
        """Bind to the request session and the Kubernetes client."""
        self._session = session
        self._k8s = clients.k8s
        self._runs = RunService(session, clients)

    async def refresh_status(self, job: AnalysisJob) -> JobStatus:
        """Fetch the K8s Job status (short TTL cache); a finished job's temp files are cleaned once."""
        changed = await refresh_recorded(
            job, job.id, analysis_status_cache, lambda: self._k8s.get_job_status(job.job_name)
        )
        if changed and job.status == JobStatus.FINISHED:
            await anyio.to_thread.run_sync(job.cleanup_temp_files)
        return job.status

    async def list_jobs(self, experiment_id: str, simulation_path: str | None = None) -> Sequence[AnalysisJob]:
        """List the experiment's analysis jobs (optionally of one simulation), refreshed."""
        stmt = AnalysisJob.query().filter_by(experiment_id=experiment_id)
        if simulation_path:
            stmt = stmt.filter_by(simulation_path=simulation_path)
        jobs = (await self._session.execute(stmt)).scalars().all()
        await gather(*(self.refresh_status(job) for job in jobs))
        return jobs

    async def get(self, experiment_id: str, job_id: str, *, refresh: bool = True) -> AnalysisJob:
        """
        Get one analysis job.

        Raises:
            NotFound: If the job does not exist in the experiment.
        """
        stmt = AnalysisJob.query().filter_by(experiment_id=experiment_id, id=job_id)
        job = (await self._session.execute(stmt)).scalars().first()
        if job is None:
            raise NotFound(f"Analysis job {job_id} in experiment {experiment_id} not found")
        if refresh:
            await self.refresh_status(job)
        return job

    async def submit(
        self,
        experiment: Experiment,
        simulation_path: str,
        analysis_name: AnalysisType,
        preprocessing_mode: PreprocessingMode,
    ) -> AnalysisJob:
        """
        Start an analysis K8s Job of a simulation's trajectory, replacing the simulation's previous analyses.

        Raises:
            Forbidden: If the namespace quota has no room for the Job.
        """
        trajectory, structure, topology = await anyio.to_thread.run_sync(
            analysis_inputs, experiment, simulation_path, preprocessing_mode
        )
        previous_jobs = [j for j in experiment.analysis_jobs if j.simulation_path == simulation_path]
        for prev in previous_jobs:
            with suppress(Exception):  # job may already be cleaned up by K8s
                await self._k8s.delete_job(prev.job_name)
            await anyio.to_thread.run_sync(prev.cleanup_temp_files)
            await self._session.delete(prev)
        await self._session.flush()

        job_id = str(uuid.uuid4())[:12]

        # Snapshot the run's progress now: the inputs copied at job start are
        # exactly the data this analysis will cover.
        run_job = await self._runs.find(experiment.id, simulation_path)
        sim_progress: float | None = None
        if run_job is not None:
            await self._runs.refresh_status(run_job)
            nsteps, done = await anyio.to_thread.run_sync(lambda: (run_job.nsteps, run_job.nsteps_done))
            if nsteps is not None and nsteps > 0 and done is not None:
                sim_progress = min(1.0, done / nsteps)

        command = format_mwf_analysis_command(
            analysis_name=analysis_name,
            structure_file=structure,
            trajectory_file=trajectory,
            topology_file=topology,
            preprocessing_mode=preprocessing_mode,
            simulation_path=simulation_path,
            engine=experiment.engine,
        )

        an_cpu = parse_cpu(ANALYSIS_RESOURCES["requests"]["cpu"])
        an_mem = parse_memory(ANALYSIS_RESOURCES["requests"]["memory"])
        an_cpu_limit = parse_cpu(ANALYSIS_RESOURCES["limits"]["cpu"])
        an_mem_limit = parse_memory(ANALYSIS_RESOURCES["limits"]["memory"])
        if msg := await self._k8s.check_quota_headroom(an_cpu, an_mem, an_cpu_limit, an_mem_limit):
            raise Forbidden(f"Cannot start analysis: {msg}")

        await self._k8s.create_job(
            name=f"analysis-{job_id}",
            image=ANALYSIS_IMAGE,
            experiment_id=experiment.id,
            command=command,
            resources=ANALYSIS_RESOURCES,
        )

        job = AnalysisJob(
            id=job_id,
            experiment_id=experiment.id,
            experiment=experiment,
            simulation_path=simulation_path,
            analysis_name=analysis_name,
            structure_file=structure.as_posix() if structure else None,
            trajectory_file=trajectory.as_posix(),
            topology_file=topology.as_posix() if topology else None,
            sim_progress=sim_progress,
        )
        self._session.add(job)
        await self._session.commit()

        logger.info(f"Started analysis job {job_id} ({analysis_name}) for experiment {experiment.id}")
        await self.refresh_status(job)
        return job

    async def logs(self, experiment_id: str, job_id: str, tail: int) -> str:
        """K8s pod logs of an analysis job, trimmed to start at the workflow start marker."""
        job = await self.get(experiment_id, job_id, refresh=False)
        logs = await self._k8s.get_job_logs(job.job_name, tail_lines=tail)
        idx = logs.find(_WORKFLOW_START_MARKER)
        return logs[idx:] if idx != -1 else logs

    async def delete_remote(self, job: AnalysisJob) -> None:
        """Delete the K8s job and clean up any temporary files it left behind (the caller deletes the row)."""
        await self._k8s.delete_job(job.job_name)
        await anyio.to_thread.run_sync(job.cleanup_temp_files)

    async def delete(self, experiment_id: str, job_id: str) -> None:
        """Delete an analysis job and its temporary files."""
        job = await self.get(experiment_id, job_id, refresh=False)
        await self.delete_remote(job)
        await self._session.delete(job)
        await self._session.commit()


AnalysisServiceDep = Annotated[AnalysisService, Depends()]
