"""GROMACS runs: submission, checkpoint extension, and logs."""

import logging
from pathlib import Path
from typing import Annotated, ClassVar

import anyio
from core.config import DATA_DIR, S3_BUCKET
from core.enums import DeviceType, Engine, JobStatus
from core.errors import BadRequest
from core.utils import strip_run_control_args
from core.validators import check_log_type
from fastapi import Depends
from sqlalchemy.exc import IntegrityError

from modules.experiments.dependencies import get_experiment_or_404
from modules.jobs.gmx.models import GromacsJob
from modules.jobs.models import SimulationJob
from modules.jobs.runs import RunService
from modules.simulations.manifest import Simulation, check_simulation_path

logger = logging.getLogger(__name__)

# TODO: remove as soon as user testing is done (also drop the persisted nsteps). Force all runs to 500k steps.
FORCED_NSTEPS = 500000


class GromacsService(RunService[GromacsJob]):
    """GROMACS runs of an experiment's simulations."""

    model: ClassVar[type[SimulationJob]] = GromacsJob
    label: ClassVar[str] = "GROMACS"

    async def submit(
        self, experiment_id: str, simulation_path: str, pme: DeviceType, nb: DeviceType, np: int, ntomp: int
    ) -> GromacsJob:
        """
        Start a run from the simulation manifest, replacing a terminal run.

        The TPR path and ``extra_args`` are derived from the manifest and passed
        to MDRun; only ``simulation_path`` and compute settings are persisted.
        A live run is a 409 (`replace_terminal_run`).
        """
        check_simulation_path(simulation_path)
        experiment = await get_experiment_or_404(self._session, experiment_id)
        await self.replace_terminal_run(experiment.id, simulation_path)

        simulation = Simulation.get(experiment.id, simulation_path, experiment)
        simulation.require_files(["run_input"])
        tpr_rel_path = simulation.resolved_files["run_input"]
        extra_args = f"{strip_run_control_args(simulation.extra_args)} -nsteps {FORCED_NSTEPS}"

        mdrun_job = await self._mdrun.create_gmx_job(
            experiment_id=experiment.id,
            tpr_name=tpr_rel_path,
            bucket_name=S3_BUCKET,
            pme=pme.value,
            nb=nb.value,
            np=np,
            ntomp=ntomp,
            extra_args=extra_args,
        )
        job = GromacsJob(
            id=mdrun_job["id"],
            simulation_path=simulation_path,
            pme=pme,
            nb=nb,
            np=np,
            ntomp=ntomp,
            experiment_id=experiment.id,
            experiment=experiment,
            engine=Engine.GMX,
            _last_known_status=JobStatus.PENDING,
            _nsteps=FORCED_NSTEPS,
        )
        await self.commit_new_run(job, simulation)
        logger.info(f"Started GROMACS job {job.id} for experiment {experiment.id} (simulation {simulation_path})")
        return job

    async def extend(self, experiment_id: str, simulation_path: str, nsteps: int) -> GromacsJob:
        """
        Extend the simulation's run by ``nsteps`` additional steps, resuming from its checkpoint.

        The run row is replaced (delete+insert) so its PK keeps naming the current
        MDRun job; the result files and the appended log are untouched.

        Raises:
            BadRequest: No run, live run, missing checkpoint, manifest contains ``-cpi``, or concurrent extend.
        """
        experiment = await get_experiment_or_404(self._session, experiment_id)
        latest = await self.find(experiment.id, simulation_path)
        if latest is None:
            raise BadRequest("No run exists for this simulation yet; extend requires a finished or stopped run.")
        await self.refresh_status(latest)
        if latest.is_live:
            raise BadRequest("The run is still active; stop it before extending.")

        simulation = Simulation.get(experiment.id, simulation_path, experiment)
        simulation.require_files(["run_input"])
        tpr_rel_path = simulation.resolved_files["run_input"]
        deffnm = tpr_rel_path.removesuffix(".tpr")

        checkpoint = DATA_DIR / experiment.id / f"{deffnm}.cpt"
        if not await anyio.Path(checkpoint).exists():
            raise BadRequest(
                f"No checkpoint file ({checkpoint.name}) found to resume from; it may still be syncing — try again shortly."
            )

        try:
            base_args = strip_run_control_args(simulation.extra_args)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc

        previous_total, progress = await anyio.to_thread.run_sync(lambda: (latest.nsteps, latest.nsteps_done))
        if previous_total is None:
            raise BadRequest("Cannot determine the previous run's total step count from its log.")

        # Anchor on actual progress, not the previous target: a stopped run
        # resumes from where it stood, so "extend by N" means N more steps from
        # that point. Read before the new block appends to the shared log.
        base = progress if progress is not None else previous_total

        # mdrun -cpi counts -nsteps as ADDITIONAL steps from the checkpoint step.
        # A cumulative total here would over-run by all previous progress.
        total = base + nsteps
        cpt_name = f"{Path(tpr_rel_path).name.removesuffix('.tpr')}.cpt"
        extra_args = " ".join(filter(None, [base_args, f"-cpi {cpt_name}", f"-nsteps {nsteps}"]))

        mdrun_job = await self._mdrun.create_gmx_job(
            experiment_id=experiment.id,
            tpr_name=tpr_rel_path,
            bucket_name=S3_BUCKET,
            pme=latest.pme.value,
            nb=latest.nb.value,
            np=latest.np,
            ntomp=latest.ntomp,
            extra_args=extra_args,
        )

        job = GromacsJob(
            id=mdrun_job["id"],
            simulation_path=simulation_path,
            pme=latest.pme,
            nb=latest.nb,
            np=latest.np,
            ntomp=latest.ntomp,
            experiment_id=experiment.id,
            engine=Engine.GMX,
            _last_known_status=JobStatus.PENDING,
            _nsteps=total,
            _init_step=base,
        )
        await self._session.delete(latest)
        # Flush first: one flush inserts before deletes, tripping the unique constraint.
        await self._session.flush()
        job.experiment = experiment
        self._session.add(job)
        try:
            await self._session.commit()
        except IntegrityError:
            # Another request committed the row first; delete our unreferenced cluster job.
            await self._session.rollback()
            await self._mdrun.delete_job(job.MDRUN_ENGINE, mdrun_job["id"])
            raise BadRequest("Another extension of this simulation is already in progress.") from None
        logger.info(
            f"Extended GROMACS simulation {simulation_path} (experiment {experiment.id}) "
            f"by {nsteps} steps to {total} as job {job.id}"
        )
        await self.refresh_status(job)
        return job

    async def log(self, experiment_id: str, simulation_path: str, log_type: str, tail: int) -> str:
        """Tail of one of the run's log streams (`gmx`, `stdout`, `stderr`)."""
        job = await self.get(experiment_id, simulation_path, refresh=False)
        log_type = log_type.lower()
        check_log_type(log_type)
        return await anyio.to_thread.run_sync(job.get_log, log_type, tail)


GromacsServiceDep = Annotated[GromacsService, Depends()]
