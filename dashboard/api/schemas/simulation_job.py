from models import SimulationJob

from .base import BaseAutoSchema


class SimulationJobSchema(BaseAutoSchema):
    """Polymorphic schema for serializing SimulationJob model instances."""

    class Meta:
        """Schema configuration."""

        model = SimulationJob
        load_instance = True
        include_fk = True
