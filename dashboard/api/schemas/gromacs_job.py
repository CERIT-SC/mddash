from models import GromacsJob

from .base import BaseAutoSchema


class GromacsJobSchema(BaseAutoSchema):
    """Schema for serializing GromacsJob model instances."""

    class Meta:
        """Schema configuration."""

        model = GromacsJob
        load_instance = True
        include_fk = True
