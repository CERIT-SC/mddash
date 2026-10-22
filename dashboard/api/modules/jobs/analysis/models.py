import logging
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self

import sqlalchemy as sa
from core.config import DATA_DIR
from core.db import Base
from core.enums import AnalysisType
from sqlalchemy import Select, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from modules.jobs.analysis.command import ANALYSIS_RUNTIME_PREP_TASKS, get_incomplete_task_dirs
from modules.jobs.analysis.results import ANALYSIS_RESULT_PREFIX, ANALYSIS_RESULT_SUFFIX, MWF_INPUTS_DIR, mwf_output_dir
from modules.jobs.status import RecordedStatus

if TYPE_CHECKING:
    from modules.experiments.models import Experiment


logger = logging.getLogger(__name__)


class AnalysisJob(RecordedStatus, Base):
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

    # Never lazy-loads (async); queries for jobs alone load it via `query()`.
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="analysis_jobs", lazy="raise_on_sql")

    @classmethod
    def query(cls) -> "Select[tuple[Self]]":
        """Select analysis jobs together with their experiments."""
        return select(cls).options(selectinload(cls.experiment))

    @property
    def job_name(self) -> str:
        """Name of the analysis K8s Job."""
        return f"analysis-{self.id}"

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
