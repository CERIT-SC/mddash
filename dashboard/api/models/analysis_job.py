import logging
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cache import analysis_status_cache
from cachetools import cached
from clients import k8s
from config import ANALYSIS_IMAGE, DATA_DIR
from enums import AnalysisType, JobStatus
from extensions import db
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .experiment import Experiment


logger = logging.getLogger(__name__)

ANALYSIS_RESULT_PREFIX = "mda."
ANALYSIS_RESULT_SUFFIX = ".json"
MWF_DIR = "mwf_analyses"

# Energies needs atomic charges from a topology file (.tpr, .top, .prmtop, .psf).
TOPOLOGY_REQUIRED_ANALYSES = {AnalysisType.ENERGIES}


def find_result_file(experiment_id: str, name: str) -> Path | None:
    """Find a result file by normalized name under the mwf output directory."""
    filename = f"{ANALYSIS_RESULT_PREFIX}{name.replace('-', '_')}{ANALYSIS_RESULT_SUFFIX}"
    mwf_dir = DATA_DIR / experiment_id / MWF_DIR
    if not mwf_dir.is_dir():
        return None
    matches = list(mwf_dir.rglob(filename))
    return matches[0] if matches else None


def list_result_files(experiment_id: str) -> list[Path]:
    """List all mda.*.json result files under the mwf output directory."""
    mwf_dir = DATA_DIR / experiment_id / MWF_DIR
    if not mwf_dir.is_dir():
        return []
    return sorted(mwf_dir.rglob(f"{ANALYSIS_RESULT_PREFIX}*{ANALYSIS_RESULT_SUFFIX}"))


class AnalysisJob(db.Model):  # type: ignore
    """On-demand MD analysis job running mddb-workflow in a K8s Job."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)

    analysis_name: Mapped[AnalysisType] = mapped_column(db.Enum(AnalysisType), nullable=False)
    structure_file: Mapped[str] = mapped_column(db.String(255), nullable=False)
    trajectory_file: Mapped[str] = mapped_column(db.String(255), nullable=False)
    topology_file: Mapped[str | None] = mapped_column(db.String(255), nullable=True)

    _last_known_status: Mapped[JobStatus | None] = mapped_column("last_known_status", db.Enum(JobStatus), nullable=True)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="analysis_jobs")

    @property
    def _job_name(self) -> str:
        return f"analysis-{self.id}"

    @property
    @cached(cache=analysis_status_cache)
    def status(self) -> JobStatus:
        """Current status of the K8s job."""
        if self._last_known_status is not None and self._last_known_status in {JobStatus.TERMINATED, JobStatus.ERROR}:
            return self._last_known_status

        try:
            fetched = k8s.get_job_status(self._job_name)
            if fetched not in {self._last_known_status, JobStatus.UNKNOWN}:
                self._last_known_status = fetched
                db.session.commit()
            return fetched
        except Exception:
            logger.exception(f"Error fetching analysis job status for {self.id}")
            if self._last_known_status:
                return self._last_known_status
            return JobStatus.UNKNOWN

    @property
    def results(self) -> list[str]:
        """List available analysis result names by scanning mwf output directory."""
        return [
            f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)].replace("_", "-")
            for f in list_result_files(self.experiment_id)
        ]

    @classmethod
    def start(
        cls,
        experiment: "Experiment",
        analysis_name: AnalysisType,
        structure_file: str,
        trajectory_file: str,
        topology_file: str | None = None,
    ) -> "AnalysisJob":
        """
        Start an analysis K8s Job for a single analysis type.

        Args:
            experiment: The experiment to run analysis on.
            analysis_name: The mwf analysis task name (e.g. "rmsds", "pca").
            structure_file: Relative path to the structure file within the experiment dir.
            trajectory_file: Relative path to the trajectory file within the experiment dir.
            topology_file: Optional topology file for charge-dependent analyses (energies).

        Returns:
            The created AnalysisJob instance.
        """
        previous_jobs = cls.query.filter_by(experiment_id=experiment.id).all()
        for prev in previous_jobs:
            with suppress(Exception):  # job may already be cleaned up by K8s
                k8s.delete_job(f"analysis-{prev.id}")
            db.session.delete(prev)
        db.session.flush()

        job_id = str(uuid.uuid4())[:12]
        job_name = f"analysis-{job_id}"

        # conda run needed because create_job uses sh -c which bypasses the ENTRYPOINT.
        # mwf_analyses/ is the MD dir; mwf forbids MD dir == project dir.
        # No -k flag: with a single analysis there's nothing to "keep going" to,
        # and it masks errors (mwf exits 0 even on InputError).
        top_flag = f"-top '{topology_file}'" if topology_file else "-top no"
        command = (
            f"mkdir -p mwf_analyses && "
            f"printf 'name: mddash\\ntype: trajectory\\ninteractions:\\n  - auto\\n' > inputs.yaml && "
            f"TQDM_DISABLE=1 conda run --no-capture-output -n mwf_env "
            f"mwf run -dir . -stru '{structure_file}' -md mwf_analyses '{trajectory_file}' "
            f"{top_flag} -i {analysis_name}"
        )

        k8s.create_job(
            name=job_name,
            image=ANALYSIS_IMAGE,
            experiment_id=experiment.id,
            command=command,
            resources={
                "requests": {"cpu": "1000m", "memory": "2Gi"},
                "limits": {"cpu": "4000m", "memory": "8Gi"},
            },
        )

        job = AnalysisJob(
            id=job_id,  # type: ignore[call-arg]
            experiment_id=experiment.id,  # type: ignore[call-arg]
            analysis_name=analysis_name,  # type: ignore[call-arg]
            structure_file=structure_file,  # type: ignore[call-arg]
            trajectory_file=trajectory_file,  # type: ignore[call-arg]
            topology_file=topology_file,  # type: ignore[call-arg]
        )
        db.session.add(job)
        db.session.commit()

        logger.info(f"Started analysis job {job_id} ({analysis_name}) for experiment {experiment.id}")
        return job

    def delete(self) -> None:
        """Delete the K8s job."""
        k8s.delete_job(self._job_name)
