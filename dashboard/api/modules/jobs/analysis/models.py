import logging
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self

import sqlalchemy as sa
from core.config import DATA_DIR
from core.db import Base
from core.enums import AnalysisType, JobStatus
from sqlalchemy import Select, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from modules.jobs.analysis.command import ANALYSIS_RUNTIME_PREP_TASKS, get_incomplete_task_dirs
from modules.jobs.analysis.results import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, MWF_INPUTS_DIR, mwf_output_dir

if TYPE_CHECKING:
    from modules.experiments.models import Experiment


logger = logging.getLogger(__name__)


class AnalysisJob(Base):
    """On-demand MD analysis job running mddb-workflow in a K8s Job."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(sa.String(5), sa.ForeignKey("experiments.id"))
    simulation_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))

    analysis_name: Mapped[AnalysisType] = mapped_column(sa.Enum(AnalysisType), nullable=False)
    structure_file: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    trajectory_file: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    topology_file: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # Fraction of the simulation's steps available when the analysis inputs were
    # snapshotted; None when the run progress was unknown (or no run existed).
    sim_progress: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", sa.Enum(JobStatus), nullable=True)

    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="analysis_jobs", lazy="raise_on_sql")

    # Transient: status fetched by AnalysisService.refresh_status() for this request
    _fetched_status: JobStatus | None = None

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select analysis jobs together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    def record_status(self, fetched: JobStatus) -> bool:
        """Store the status read for this request; True when it persisted as the new offline fallback."""
        changed = fetched not in {self._last_known_status, JobStatus.UNKNOWN}
        if changed:
            self._last_known_status = fetched
        self._fetched_status = fetched
        return changed

    def record_status_unavailable(self) -> None:
        """Serve the last known status (the K8s Job could not be read)."""
        self._fetched_status = self._last_known_status or JobStatus.UNKNOWN

    @property
    def settled_status(self) -> JobStatus | None:
        """FINISHED or ERROR once reached: such a job never changes again."""
        status = self._last_known_status
        return status if status in {JobStatus.FINISHED, JobStatus.ERROR} else None

    @property
    def job_name(self) -> str:
        """Name of the analysis K8s Job."""
        return f"analysis-{self.id}"

    @property
    def status(self) -> JobStatus:
        """
        Current status of the K8s job, as of the last `AnalysisService.refresh_status()`.

        Raises:
            RuntimeError: If an unsettled job was not refreshed in this request.
        """
        if settled := self.settled_status:
            return settled
        if self._fetched_status is None:
            raise RuntimeError(f"Status of analysis job {self.id} read before AnalysisService.refresh_status()")
        return self._fetched_status

    def cleanup_temp_files(self) -> None:
        """Remove temporary files left in the experiment directory by a job run."""
        exp_dir = DATA_DIR / self.experiment_id

        with suppress(Exception):
            (exp_dir / "inputs.yaml").unlink()

        with suppress(Exception):
            shutil.rmtree(exp_dir / MWF_INPUTS_DIR)

        task_names = ANALYSIS_RUNTIME_PREP_TASKS.get(self.analysis_name, ())
        for task_name in task_names:
            for incomplete_dir in get_incomplete_task_dirs(task_name):
                with suppress(Exception):
                    shutil.rmtree(exp_dir / incomplete_dir)

        mwf_dir = exp_dir / mwf_output_dir(self.simulation_path)
        if mwf_dir.is_dir():
            result_pattern = f"{ANALYSIS_RESULT_PREFIX}*{ANALYSIS_RESULT_SUFFIX}"
            for path in mwf_dir.rglob("*"):
                if path.is_file() and not path.match(result_pattern):
                    with suppress(Exception):
                        path.unlink()
            # bottom-up so inner empty dirs are removed before their parents
            for path in sorted(mwf_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    with suppress(Exception):
                        path.rmdir()
