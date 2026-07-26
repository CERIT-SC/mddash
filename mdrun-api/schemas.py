from collections.abc import Callable

from enums import AmberBinary, DeviceType, EwaldPreset
from marshmallow import Schema, ValidationError, fields, post_load, validate


def _enum_from_string(from_string: Callable[[str], object], value: str, field_name: str) -> object:
    try:
        return from_string(value)
    except ValueError:
        raise ValidationError(f"Invalid {field_name}: {value!r}")


class GmxJobCreateRequestSchema(Schema):
    """Schema for validating GROMACS job creation requests."""

    experiment_id = fields.Str(required=True)
    tpr_name = fields.Str(required=True)
    bucket_name = fields.Str(required=True)
    pme = fields.Str(required=True)
    nb = fields.Str(required=True)
    np = fields.Int(required=True, validate=validate.Range(min=1))
    ntomp = fields.Int(required=True, validate=validate.Range(min=1))
    extra_args = fields.Str(load_default="")

    @post_load
    def _convert_enums(self, data: dict, **_kwargs: object) -> dict:
        data["pme"] = _enum_from_string(DeviceType.from_string, data["pme"], "pme")
        data["nb"] = _enum_from_string(DeviceType.from_string, data["nb"], "nb")
        return data


class AmberJobCreateRequestSchema(Schema):
    """Schema for validating AMBER job creation requests."""

    experiment_id = fields.Str(required=True)
    prmtop_name = fields.Str(required=True)
    inpcrd_name = fields.Str(required=True)
    mdin_name = fields.Str(required=True)
    bucket_name = fields.Str(required=True)
    binary = fields.Str(required=True)
    np = fields.Int(required=True, validate=validate.Range(min=1))
    ntomp = fields.Int(required=True, validate=validate.Range(min=1))
    ewald = fields.Str(required=True)
    extra_args = fields.Str(load_default="")

    @post_load
    def _convert_enums(self, data: dict, **_kwargs: object) -> dict:
        data["binary"] = _enum_from_string(AmberBinary.from_string, data["binary"], "binary")
        data["ewald"] = _enum_from_string(EwaldPreset.from_string, data["ewald"], "ewald")
        return data
