import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Self

import httpx
import sqlalchemy as sa
from clients import tuner
from core.cache import tuner_last_known_status, tuner_status_cache
from core.db import Base
from core.enums import Engine, JobStatus
from core.errors import ApiError
from sqlalchemy import JSON, Select, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from modules.simulations.manifest import Simulation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from modules.experiments.models import Experiment

logger = logging.getLogger(__name__)


class TunerJob(Base):
    """Tuner job for optimizing MD simulation parameters (GROMACS or AMBER)."""

    __tablename__ = "tuner_jobs"

    # ID of the tune job from the tuner API (primary key)
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    # ID of the experiment this job belongs to
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    # Experiment-relative path to the .simulation.json manifest (job identity)
    simulation_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # error message if job creation failed
    error_message: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))
    # number of steps each tuning trial runs (always caller-supplied; no default, fail fast)
    nsteps: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # whether the job was stopped (preserves data but job is deleted from tuner)
    is_stopped: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    # preserved trials when job is stopped
    _preserved_trials: Mapped[list[dict] | None] = mapped_column("preserved_trials", JSON, nullable=True)

    # back-reference to the parent experiment
    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="tuner_jobs", lazy="raise_on_sql")

    # Transient: tuner status payload fetched by refresh() for this request
    _status_data: dict | None = None

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select tuner jobs together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    @property
    def engine(self) -> Engine:
        """MD engine inferred from the parent experiment."""
        return self.experiment.engine

    @property
    def tuner_status(self) -> JobStatus:
        """Status of the job on the tuner; the status dict carries raw JSON strings."""
        value = str(self._status().get("status", JobStatus.UNKNOWN))
        return JobStatus.from_string(value) if value.upper() in JobStatus.__members__ else JobStatus.UNKNOWN

    @property
    def is_live(self) -> bool:
        """A stopped job is terminal even though its status reads UNKNOWN."""
        return not self.is_stopped and self.tuner_status.is_live

    @property
    def sim_length_ns(self) -> float | None:
        """Full production simulation length (ns) reported by the tuner."""
        return self._status().get("sim_length_ns")

    @property
    def trials(self) -> list[dict]:
        """Trial jobs with their statuses."""
        if self.is_stopped and self._preserved_trials:
            return self._preserved_trials
        return self._status().get("trials", [])

    def _status(self) -> dict:
        """
        Tuner status as of the last `refresh()`; empty once stopped.

        Raises:
            RuntimeError: If a running job was not refreshed in this request.
        """
        if self.is_stopped:
            return {}
        if self._status_data is None:
            raise RuntimeError(f"Status of tuner job {self.id} read before refresh()")
        return self._status_data

    async def refresh(self) -> None:
        """
        Fetch the tuner status (short TTL cache), falling back to the last known status on errors.

        A FINISHED job is stopped (trials persisted, tuner freed); so is one the tuner no longer knows (404).
        """
        if self.is_stopped:
            return

        if (cached := tuner_status_cache.get(self.id)) is not None:
            self._status_data = cached
            return

        self._status_data = tuner_last_known_status.get(self.id, {})
        try:
            match self.engine:
                case Engine.GMX:
                    status = await tuner.gmx_poll_status(self.id)
                case Engine.AMBER:
                    status = await tuner.amber_poll_status(self.id)

            if status.get("status") == JobStatus.ERROR and not self.error_message:
                self.error_message = status.get("error") or "Tuning job failed on the tuner."

            if "status" not in status or "trials" not in status:
                raise ValueError(f"Incomplete status response from tuner for job {self.id}")

            tuner_status_cache[self.id] = status
            tuner_last_known_status[self.id] = status
            self._status_data = status

            # A finished job never changes again: persist trials and free the tuner.
            if status["status"] == JobStatus.FINISHED:
                await self.stop()

        except TimeoutError:
            logger.warning(f"Timeout fetching tuner status for job {self.id}")
        except httpx.HTTPStatusError as exc:
            # 404 means the tuner no longer has this job (reaped or restarted); stop re-polling.
            if exc.response.status_code == HTTPStatus.NOT_FOUND:
                logger.warning(f"Tuner job {self.id} not found on tuner; stopping")
                await self.stop()
            else:
                logger.exception(f"Error fetching tuner status for job {self.id}")
        except Exception:
            logger.exception(f"Error fetching tuner status for job {self.id}")

    @classmethod
    async def start(
        cls, session: "AsyncSession", experiment: "Experiment", simulation_path: str, nsteps: int
    ) -> "TunerJob":
        """
        Start a tuner job for the given experiment and simulation manifest.

        Launch files and ``extra_args`` are derived from the simulation JSON and
        passed to the tuner client; they are not persisted in the dashboard DB.

        Raises:
            ApiError: If the tuner is unavailable (upstream-unavailable).
        """
        simulation = Simulation.get(experiment.id, simulation_path, experiment)
        simulation.require_files(
            ["run_input"] if experiment.engine == Engine.GMX else ["topology", "coordinates", "control"]
        )
        extra_args = simulation.extra_args
        # TODO: drop after user testing (#166). Pin the tuner's length estimate to the forced 500k run.
        if experiment.engine == Engine.GMX:
            extra_args = f"{extra_args} -nsteps 500000".strip()

        try:
            match experiment.engine:
                case Engine.GMX:
                    response = await tuner.gmx_submit(
                        simulation.resolve_role("run_input"), nsteps=nsteps, extra_args=extra_args
                    )
                case Engine.AMBER:
                    response = await tuner.amber_submit(
                        simulation.resolve_role("topology"),
                        simulation.resolve_role("coordinates"),
                        simulation.resolve_role("control"),
                        nsteps=nsteps,
                        extra_args=extra_args,
                    )
        except httpx.HTTPError as exc:
            logger.error("Tuner submit failed for experiment %s: %s", experiment.id, exc)
            raise ApiError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Failed to submit tuning job.",
                "urn:mddash:upstream-unavailable",
                "The tuning service is unavailable; try again in a moment.",
            ) from exc

        job = cls(
            id=response["id"],
            experiment_id=experiment.id,
            experiment=experiment,
            simulation_path=simulation_path,
            nsteps=nsteps,
        )
        session.add(job)
        await session.commit()

        simulation.mark_readonly()

        logger.info(
            f"Tuner job {response['id']} started for experiment {experiment.id} "
            f"with engine {experiment.engine} (simulation {simulation_path})"
        )
        return job

    async def _delete_on_tuner(self) -> None:
        try:
            match self.engine:
                case Engine.GMX:
                    await tuner.gmx_delete_job(self.id)
                case Engine.AMBER:
                    await tuner.amber_delete_job(self.id)
        except httpx.HTTPError:
            logger.exception(f"Failed to delete tuner job {self.id}")

    async def stop(self) -> None:
        """Stop the tuner job and preserve observed trials (the caller commits)."""
        if self.is_stopped:
            return

        last = tuner_last_known_status.get(self.id, {})
        self._preserved_trials = [trial for trial in last.get("trials", []) if trial.get("performance") is not None]
        self.is_stopped = True
        await self._delete_on_tuner()
        tuner_status_cache.clear()
        logger.info(f"Stopped tuner job {self.id}")

    async def delete(self) -> None:
        """Delete the job on the tuner; a stopped job is already gone there (the caller deletes the row)."""
        if self.is_stopped:
            return
        await self._delete_on_tuner()
