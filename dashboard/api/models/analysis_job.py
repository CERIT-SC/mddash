import logging
import uuid
from datetime import datetime
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


class AnalysisJob(db.Model):  # type: ignore
    """On-demand MD analysis job running mddb-workflow in a K8s Job."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(db.String(5), db.ForeignKey("experiments.id"))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.now)

    analysis_name: Mapped[AnalysisType] = mapped_column(db.Enum(AnalysisType), nullable=False)
    structure_file: Mapped[str] = mapped_column(db.String(255), nullable=False)
    trajectory_file: Mapped[str] = mapped_column(db.String(255), nullable=False)

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
        """List available analysis result names by scanning for mda.*.json files."""
        experiment_dir = DATA_DIR / self.experiment_id
        if not experiment_dir.is_dir():
            return []

        names = []
        for f in experiment_dir.iterdir():
            if f.is_file() and f.name.startswith(ANALYSIS_RESULT_PREFIX) and f.name.endswith(ANALYSIS_RESULT_SUFFIX):
                name = f.name[len(ANALYSIS_RESULT_PREFIX) : -len(ANALYSIS_RESULT_SUFFIX)]
                names.append(name)

        return sorted(names)

    @classmethod
    def start(
        cls,
        experiment: "Experiment",
        analysis_name: AnalysisType,
        structure_file: str,
        trajectory_file: str,
    ) -> "AnalysisJob":
        """
        Start an analysis K8s Job for a single analysis type.

        Args:
            experiment: The experiment to run analysis on.
            analysis_name: The mwf analysis task name (e.g. "rmsds", "pca").
            structure_file: Relative path to the structure file within the experiment dir.
            trajectory_file: Relative path to the trajectory file within the experiment dir.

        Returns:
            The created AnalysisJob instance.
        """
        job_id = str(uuid.uuid4())[:12]
        job_name = f"analysis-{job_id}"

        # create_job wraps with sh -c which overrides the Docker ENTRYPOINT, so we
        # must activate the conda environment explicitly via conda run.
        # mwf requires the MD directory to be a subdirectory of the project directory,
        # so we create mwf_analyses/ and copy results out afterwards.
        # -i runs only the specified analysis (include-only mode).
        command = (
            f"mkdir -p mwf_analyses && "
            f"echo 'name: mddash' > inputs.yaml && "
            f"conda run --no-capture-output -n mwf_env "
            f"mwf run -dir . -stru '{structure_file}' -md mwf_analyses '{trajectory_file}' "
            f"-top no -k -i {analysis_name} -sl; "
            f"ret=$?; cp mwf_analyses/mda.*.json . 2>/dev/null; exit $ret"
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
        )
        db.session.add(job)
        db.session.commit()

        logger.info(f"Started analysis job {job_id} ({analysis_name}) for experiment {experiment.id}")
        return job

    def delete(self) -> None:
        """Delete the K8s job."""
        k8s.delete_job(self._job_name)
