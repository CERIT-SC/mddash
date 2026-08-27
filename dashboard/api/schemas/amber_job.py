from enums import AmberBinary, EwaldPreset
from marshmallow import fields
from models import AmberJob

from .base import BaseAutoSchema


class AmberJobSchema(BaseAutoSchema):
    """Schema for serializing AmberJob model instances."""

    class Meta:
        """Schema configuration."""

        model = AmberJob
        load_instance = True
        include_fk = True

    # A schema-level Meta masks the custom model converter, so enum columns would
    # dump by name (PMEMD_CUDA) — the contract and its consumers (re-run re-POSTs,
    # trial matching) use values (pmemd.cuda). Same fix as the GROMACS schema.
    binary = fields.Enum(AmberBinary, by_value=True)
    ewald = fields.Enum(EwaldPreset, by_value=True)
