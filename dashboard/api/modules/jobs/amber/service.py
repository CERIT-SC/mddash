"""AMBER runs: submission and logs."""

import logging
from typing import Annotated, ClassVar

import anyio
from core.config import S3_BUCKET
from core.enums import AmberBinary, Engine, EwaldPreset, JobStatus
from core.errors import BadRequest
from fastapi import Depends

from modules.experiments.dependencies import get_experiment_or_404
from modules.jobs.amber.models import AmberJob
from modules.jobs.models import SimulationJob
from modules.jobs.runs import RunService
from modules.simulations.manifest import Simulation, check_simulation_path

logger = logging.getLogger(__name__)


class AmberService(RunService[AmberJob]):
    """AMBER runs of an experiment's simulations."""

    model: ClassVar[type[SimulationJob]] = AmberJob
    label: ClassVar[str] = "AMBER"

    async def submit(
        self, experiment_id: str, simulation_path: str, binary: str, ewald: str, np: int, ntomp: int
    ) -> AmberJob:
        """
        Start a run from the simulation manifest, replacing a terminal run.

        A live run is a 409 (`reject_live_run`).

        Raises:
            BadRequest: If the binary or Ewald preset is unknown.
        """
        check_simulation_path(simulation_path)
        experiment = await get_experiment_or_404(self._session, experiment_id)
        prior = await self.reject_live_run(experiment.id, simulation_path)
        try:
            amber_binary = AmberBinary.from_string(binary)
            ewald_preset = EwaldPreset.from_string(ewald)
        except ValueError as exc:
            raise BadRequest("Invalid compute parameters.") from exc
        if prior is not None:
            await self.remove(experiment.id, simulation_path)

        simulation = await anyio.to_thread.run_sync(
            Simulation.load_ready, experiment, simulation_path, ["topology", "coordinates", "control"]
        )
        resolved = simulation.resolved_files

        mdrun_job = await self._mdrun.create_amber_job(
            experiment_id=experiment.id,
            prmtop_name=resolved["topology"],
            inpcrd_name=resolved["coordinates"],
            mdin_name=resolved["control"],
            bucket_name=S3_BUCKET,
            binary=amber_binary.value,
            ewald=ewald_preset.value,
            np=np,
            ntomp=ntomp,
            extra_args=simulation.extra_args,
        )
        job = AmberJob(
            id=mdrun_job["id"],
            simulation_path=simulation_path,
            binary=amber_binary,
            ewald=ewald_preset,
            np=np,
            ntomp=ntomp,
            experiment_id=experiment.id,
            experiment=experiment,
            engine=Engine.AMBER,
            _last_known_status=JobStatus.PENDING,
        )
        await self.commit_new_run(job, simulation)
        logger.info(f"Started AMBER job {job.id} for experiment {experiment.id} (simulation {simulation_path})")
        return job

    async def log(self, experiment_id: str, simulation_path: str, log_type: str, tail: int) -> str:
        """Tail of one of the run's log streams (`mdout`, `mdinfo`, `stdout`, `stderr`)."""
        job = await self.get(experiment_id, simulation_path, refresh=False)
        return await anyio.to_thread.run_sync(job.get_log, log_type.lower(), tail)


AmberServiceDep = Annotated[AmberService, Depends()]
