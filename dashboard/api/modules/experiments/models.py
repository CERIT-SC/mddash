from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from core.config import DATA_DIR, MDREPO_RECORD_NAME, MDREPO_URL
from core.db import Base
from core.enums import Engine, JobStatus, SourceType
from core.utils import file_download_url, get_du_size
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modules.experiments.sources import list_simulations

if TYPE_CHECKING:
    from modules.jobs.analysis.models import AnalysisJob
    from modules.jobs.models import SimulationJob
    from modules.jobs.tuner.models import TunerJob
    from modules.notebooks.models import Notebook
    from modules.simulations.manifest import Simulation


class Experiment(Base):
    """
    A molecular dynamics experiment, from setup through execution to publication.

    The ID is a unique 5-character identifier that is also the experiment directory name.
    Remote state (pods, jobs, MDRepo, archive Jobs) is fetched by `ExperimentService.refresh()`;
    properties then only read the DB row, its loaded jobs, and the experiment files.
    """

    __tablename__ = "experiments"

    # unique ID of the experiment, also used as the directory name
    id: Mapped[str] = mapped_column(sa.String(5), primary_key=True)
    # creation time
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=lambda: datetime.now(UTC))
    # last modification time
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # name of the experiment
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # display name of the curated notebook module used at creation; None = custom workflow
    module_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # category snapshot of the curated module at creation (drives the card icon); None = custom workflow
    module_category: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    source_type: Mapped[SourceType | None] = mapped_column(sa.Enum(SourceType), nullable=True)
    # RCSB accession, or the resolved download URL for URL/repo sources
    source_ref: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    # original uploaded filenames (source_type=file only); creation history, not derived state
    source_files: Mapped[list[str] | None] = mapped_column(sa.JSON, nullable=True)
    # git repository URL containing setup notebooks (nullable for legacy experiments) TODO: make non-nullable (breaks db migration)
    notebooks_repo: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    # ID of the experiment in MDRepo
    mdrepo_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    # Whether the experiment is published in MDRepo (True=published, False=draft, None=not in MDRepo)
    mdrepo_published: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    # Molecular dynamics engine (GMX or AMBER)
    engine: Mapped[Engine] = mapped_column(sa.Enum(Engine), nullable=False, default=Engine.GMX)

    # Archive state: archived_at is the durable flag (NULL = active); the other three
    # snapshot card state at archive-submit time and double as "archive submitted" markers.
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    archived_size_bytes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    archived_step: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    archived_status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)

    # Child rows load with the experiment (async sessions cannot lazy-load on attribute access).
    notebook: Mapped["Notebook"] = relationship(
        "Notebook", back_populates="experiment", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    tuner_jobs: Mapped[list["TunerJob"]] = relationship(
        "TunerJob", back_populates="experiment", cascade="all, delete-orphan", lazy="selectin"
    )
    # Base relationship for JTI; subclass columns load via polymorphic selectin
    simulation_jobs: Mapped[list["SimulationJob"]] = relationship(
        "SimulationJob", back_populates="experiment", cascade="all, delete-orphan", lazy="selectin"
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob", back_populates="experiment", cascade="all, delete-orphan", lazy="selectin"
    )

    # Transient per-request state filled by ArchiveService.refresh_state() / memoized derivations
    _archive_state: str | None = None
    _archive_state_refreshed: bool = False
    _memo_step: tuple[int, str] | None = None
    _memo_latest: "Simulation | None" = None
    _memo_latest_scanned: bool = False

    @property
    def source(self) -> dict | None:
        """
        Structured provenance for API payloads; None on legacy rows.

        ``files`` lists source artifacts still downloadable (pdb sources always
        download to ``input.pdb``); ``file_count`` is the creation-time upload
        count that survives file deletions.
        """
        if self.source_type is None:
            return None

        result: dict[str, object] = {"type": str(self.source_type)}
        if self.source_ref:
            if self.source_type == SourceType.PDB and not self.source_ref.startswith(("http://", "https://")):
                result["pdb_id"] = self.source_ref
            else:
                result["url"] = self.source_ref
        if self.source_type == SourceType.FILE:
            result["file_count"] = len(self.source_files or [])

        names = ["input.pdb"] if self.source_type == SourceType.PDB else sorted(self.source_files or [])
        files: list[dict[str, object]] = []
        for name in names:
            try:
                size = (path := DATA_DIR / self.id / name).stat().st_size
            except OSError:
                continue  # Raced deletion. Never leak a broken entry into the payload.
            if not path.is_file():
                continue
            files.append({"name": name, "size": size, "path": name, "url": file_download_url(self.id, name)})
        result["files"] = files
        return result

    @property
    def step(self) -> int:
        """Step of the experiment based on its current state."""
        return self._step_status()[0]

    @property
    def status(self) -> str:
        """Status of the experiment based on its current state."""
        return self._step_status()[1]

    @property
    def can_publish(self) -> bool:
        """
        Whether the experiment has anything publishable.

        Publishing is experiment-level (the MDRepo upload covers the whole
        experiment), so this lives here rather than on a simulation: unlocked
        once a draft/record exists, or once any run finished or was stopped
        anywhere in the experiment (stopped ⇔ finished: partial results are
        publishable). The wizard also holds Publish while the SELECTED
        simulation is live. This flag cannot express that per-simulation concern.
        """
        return self.mdrepo_id is not None or any(
            job.status in {JobStatus.FINISHED, JobStatus.STOPPED} for job in self.simulation_jobs
        )

    @property
    def mdrepo_record_url(self) -> str | None:
        """The MDRepo record URL if published."""
        if self.mdrepo_id:
            return f"{MDREPO_URL}/{MDREPO_RECORD_NAME}/uploads/{self.mdrepo_id}"
        return None

    @property
    def size_bytes(self) -> int | None:
        """Last size of the experiment directory measured by the du monitor, in bytes."""
        if self.archived_at is not None:
            return self.archived_size_bytes
        return get_du_size(DATA_DIR / self.id)

    # --- derived state ------------------------------------------------------------

    @property
    def latest_simulation_path(self) -> str | None:
        """Path of the latest simulation manifest; step/status and card details inherit from it."""
        latest = self._latest_simulation()
        return latest.simulation_path if latest else None

    def _latest_simulation(self) -> "Simulation | None":
        """Most recently interacted-with simulation (by ``Simulation.last_activity``), scanned once per instance."""
        if not self._memo_latest_scanned:
            simulations = list_simulations(self)
            self._memo_latest = max(simulations, key=lambda sim: sim.last_activity) if simulations else None
            self._memo_latest_scanned = True
        return self._memo_latest

    def _step_status(self) -> tuple[int, str]:
        """
        Publish state overrides; otherwise inherit the latest simulation's (step, status).

        Returns:
            (step, status): step is the phase index (0-4, with publish 4).
        """
        if self._memo_step is None:
            self._memo_step = self._compute_step_status()
        return self._memo_step

    def _compute_step_status(self) -> tuple[int, str]:
        if self.archived_at is not None and self.archived_step is not None:
            # Files are gone; serve the snapshot taken at archive-submit time.
            return self.archived_step, self.archived_status or "archived"

        if self.mdrepo_published is True:
            return 4, "published"

        if self.mdrepo_published is False:
            return 4, "publishing"

        if latest := self._latest_simulation():
            return latest.step_status

        return 0, "setup"

    # --- archiving ----------------------------------------------------------------

    @property
    def archive_state(self) -> str | None:
        """
        One of: None, archiving, archived, restoring, archive_failed, restore_failed.

        Raises:
            RuntimeError: If an archive-marked experiment was not refreshed in this request.
        """
        if self.archived_at is None and self.archived_step is None:
            return None
        if not self._archive_state_refreshed:
            raise RuntimeError(f"Archive state of experiment {self.id} read before ArchiveService.refresh_state()")
        return self._archive_state

    def record_archive_state(self, state: str | None) -> None:
        """Store the archive state reconciled for this request."""
        self._archive_state = state
        self._archive_state_refreshed = True
