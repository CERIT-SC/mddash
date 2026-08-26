from enums import AnalysisType
from marshmallow import fields as ma_fields
from models import AnalysisJob

from .base import BaseAutoSchema


class AnalysisJobSchema(BaseAutoSchema):
    """Schema for serializing AnalysisJob model instances."""

    class Meta:
        """Schema configuration."""

        model = AnalysisJob
        load_instance = True
        include_fk = True

    # marshmallow-sqlalchemy auto-detects Enum columns as by-name dumps
    # ("RMSDS"); the API contract exposes the enum values ("rmsds").
    analysis_name = ma_fields.Enum(AnalysisType, by_value=True)
