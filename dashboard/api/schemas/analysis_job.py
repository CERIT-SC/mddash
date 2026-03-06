from models import AnalysisJob

from .base import BaseAutoSchema


class AnalysisJobSchema(BaseAutoSchema):
    """Schema for serializing AnalysisJob model instances."""

    class Meta:
        """Schema configuration."""

        model = AnalysisJob
        load_instance = True
        include_fk = True
