from marshmallow import fields
from models import Notebook

from .base import BaseAutoSchema


class NotebookSchema(BaseAutoSchema):
    """Schema for serializing Notebook model instances."""

    # Override auto-generated EnumField to serialize by value ("1x") not name ("SMALL")
    tier = fields.String(allow_none=True)
    # Computed property, declared so the datetime dumps as ISO 8601 (matches format: date-time)
    started_at = fields.DateTime(allow_none=True)

    class Meta:
        """Schema configuration."""

        model = Notebook
        load_instance = True
        include_fk = True
