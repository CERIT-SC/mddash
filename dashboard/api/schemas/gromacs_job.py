from enums import DeviceType
from marshmallow import fields
from models import GromacsJob

from .base import BaseAutoSchema


class GromacsJobSchema(BaseAutoSchema):
    """Schema for serializing GromacsJob model instances."""

    class Meta:
        """Schema configuration."""

        model = GromacsJob
        load_instance = True
        include_fk = True

    # A schema-level Meta masks the custom model converter, so enum columns would
    # dump by name (CPU/GPU) — the contract and all counterparties use lowercase.
    # Same explicit fix as `engine` in the sibling schemas.
    pme = fields.Enum(DeviceType, by_value=True)
    nb = fields.Enum(DeviceType, by_value=True)
