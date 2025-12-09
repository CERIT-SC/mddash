from models import Notebook

from .base import BaseAutoSchema


class NotebookSchema(BaseAutoSchema):
    """Schema for serializing Notebook model instances."""

    class Meta:
        """Schema configuration."""

        model = Notebook
        load_instance = True
        include_fk = True
