from enums import Engine
from marshmallow import fields
from models import SimulationJob

from .base import BaseAutoSchema


class SimulationJobSchema(BaseAutoSchema):
    """Polymorphic schema for serializing SimulationJob model instances."""

    engine = fields.Enum(Engine, by_value=True)

    class Meta:
        """Schema configuration."""

        model = SimulationJob
        load_instance = True
        include_fk = True
