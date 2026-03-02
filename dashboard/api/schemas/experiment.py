from marshmallow import fields, pre_dump
from models import Experiment

from .base import BaseAutoSchema


class ExperimentSchema(BaseAutoSchema):
    """Schema for serializing Experiment model instances."""

    notebook = fields.Nested("NotebookSchema", allow_none=False)
    tuner_jobs = fields.Nested("TunerJobSchema", many=True)
    gromacs_jobs = fields.Nested("GromacsJobSchema", many=True)

    class Meta:
        """Schema configuration."""

        model = Experiment
        load_instance = True
        include_relationships = True

    @pre_dump
    def sync_mdrepo(self, data: Experiment, **kwargs: dict) -> Experiment:  # noqa: ARG002
        """
        Sync MDRepo status before serialization.

        Returns:
            Experiment: The same experiment instance after syncing its MDRepo status.
        """
        data._sync_mdrepo_status()  # noqa: SLF001
        return data
