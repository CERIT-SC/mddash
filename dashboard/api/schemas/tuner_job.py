from models import TunerJob

from .base import BaseAutoSchema


class TunerJobSchema(BaseAutoSchema):
    """Schema for serializing TunerJob model instances."""

    class Meta:
        """Schema configuration."""

        model = TunerJob
        load_instance = True
        include_fk = True
