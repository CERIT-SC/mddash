from enums import Engine
from marshmallow import fields, pre_dump
from models import Experiment

from .base import BaseAutoSchema


class ExperimentSchema(BaseAutoSchema):
    """Schema for serializing Experiment model instances."""

    engine = fields.Enum(Engine, by_value=True)
    size_bytes = fields.Integer(allow_none=True, dump_only=True)
    latest_simulation_path = fields.String(allow_none=True, dump_only=True)
    notebook = fields.Nested("NotebookSchema", allow_none=False)
    tuner_jobs = fields.Nested("TunerJobSchema", many=True)
    simulation_jobs = fields.Nested("SimulationJobSchema", many=True)

    class Meta:
        """Schema configuration."""

        model = Experiment
        load_instance = True
        include_relationships = True

    @pre_dump
    def sync_mdrepo(self, data: Experiment, **kwargs: dict) -> Experiment:  # ruff:ignore[unused-method-argument]
        """
        Sync MDRepo status before serialization.

        Returns:
            Experiment: The same experiment instance after syncing its MDRepo status.
        """
        data._sync_mdrepo_status()  # ruff:ignore[private-member-access]
        return data
