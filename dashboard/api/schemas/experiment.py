from marshmallow import fields
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
