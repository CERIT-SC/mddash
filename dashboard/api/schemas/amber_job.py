from models import AmberJob

from .base import BaseAutoSchema


class AmberJobSchema(BaseAutoSchema):
    """Schema for serializing AmberJob model instances."""

    class Meta:
        """Schema configuration."""

        model = AmberJob
        load_instance = True
        include_fk = True
