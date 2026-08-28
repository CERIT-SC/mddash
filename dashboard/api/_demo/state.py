"""
Demo runtime state management.

Provides typed state containers for tracking mock service state
during demo sessions. All state is held in memory and cleared on restart.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

from enums import PodStatus

from .files import MDPOSIT_DEMO_ACCESSION, MDPOSIT_DEMO_FILES

ModelType = TypeVar("ModelType")


def _default_mdposit_projects() -> dict[str, dict[str, Any]]:
    return {
        MDPOSIT_DEMO_ACCESSION: {
            "id": MDPOSIT_DEMO_ACCESSION,
            "accession": MDPOSIT_DEMO_ACCESSION,
            "title": "Demo MDPosit lysozyme trajectory",
            "description": "Offline demo project for MDPosit import flows.",
            "files": list(MDPOSIT_DEMO_FILES),
        }
    }


@dataclass
class DemoState:
    """
    Central container for all demo runtime state.

    This singleton holds all mock service state including pod statuses,
    job states, and MDRepo publication status. State is in-memory only
    and resets when the demo app restarts.
    """

    initialized: bool = False
    notebook_status: dict[str, PodStatus] = field(default_factory=dict)
    notebook_started_at: dict[str, datetime] = field(default_factory=dict)
    mdrun_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    tuner_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    analysis_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    mdrepo_records: dict[str, bool] = field(default_factory=dict)
    mdrepo_counter: int = 1
    upload_jobs: dict[str, str] = field(default_factory=dict)  # job_name -> experiment_id
    mdposit_projects: dict[str, dict[str, Any]] = field(default_factory=_default_mdposit_projects)

    def reset(self) -> None:
        """Clear all runtime state."""
        self.notebook_status.clear()
        self.notebook_started_at.clear()
        self.mdrun_jobs.clear()
        self.tuner_jobs.clear()
        self.analysis_jobs.clear()
        self.mdrepo_records.clear()
        self.mdrepo_counter = 1
        self.upload_jobs.clear()
        self.mdposit_projects = _default_mdposit_projects()
        self.initialized = False

    def get_notebook_status(self, experiment_id: str) -> PodStatus:
        """
        Get notebook pod status for an experiment.

        Returns:
            The pod status, defaults to DOWN if not found.
        """
        return self.notebook_status.get(experiment_id, PodStatus.DOWN)

    def set_notebook_status(self, experiment_id: str, status: PodStatus) -> None:
        """Set notebook pod status for an experiment."""
        self.notebook_status[experiment_id] = status

    def get_mdrun_job(self, job_id: str) -> dict[str, Any] | None:
        """
        Get MDRun job state by ID.

        Returns:
            Job state dict or None if not found.
        """
        return self.mdrun_jobs.get(job_id)

    def get_tuner_job(self, job_id: str) -> dict[str, Any] | None:
        """
        Get tuner job state by ID.

        Returns:
            Job state dict or None if not found.
        """
        return self.tuner_jobs.get(job_id)

    def is_mdrepo_published(self, record_id: str) -> bool | None:
        """
        Check if an MDRepo record is published.

        Returns:
            True if published, False if draft, None if not found.
        """
        return self.mdrepo_records.get(record_id)


# Global singleton instance
demo_state = DemoState()


def build_model(model_cls: type[ModelType], **attrs: Any) -> ModelType:  # ruff:ignore[any-type]
    """
    Build a model instance for demo seeding.

    Creates an instance and sets attributes. For SQLAlchemy models,
    uses the normal constructor but allows setting private attributes.

    Args:
        model_cls: The SQLAlchemy model class to instantiate.
        **attrs: Attributes to set on the model instance.

    Returns:
        The model instance with attributes set.
    """
    # Separate public attributes from private ones (prefixed with _)
    public_attrs = {k: v for k, v in attrs.items() if not k.startswith("_")}
    private_attrs = {k: v for k, v in attrs.items() if k.startswith("_")}

    # Create instance with public attributes
    model = model_cls(**public_attrs)

    # Set private attributes directly (these bypass __init__)
    for attr, value in private_attrs.items():
        setattr(model, attr, value)

    return model
