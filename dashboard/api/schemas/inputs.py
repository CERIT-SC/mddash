"""Request-parsing schemas for the Dashboard API."""

from enum import Enum

from enums import AnalysisType, NotebookTier, PreprocessingMode
from marshmallow import Schema, ValidationError, fields, post_load, validate


class StartNotebookSchema(Schema):
    """Schema for the POST /notebook request body."""

    tier = fields.Str(load_default=None, validate=validate.Length(min=1))
    gpu = fields.Bool(load_default=False)

    @post_load
    def _convert_tier(self, data: dict, **_kwargs: object) -> dict:
        tier = data.get("tier")
        if tier is not None:
            try:
                data["tier"] = NotebookTier(tier)
            except ValueError:
                valid = ", ".join(t.value for t in NotebookTier)
                raise ValidationError(f"Unknown notebook tier. Valid tiers: {valid}", field_name="tier")
        return data


class PublishSchema(Schema):
    """Schema for the POST /experiments/<id>/publish request body."""

    target = fields.Str(load_default="invenio", validate=validate.Length(min=1))
    simulation_path = fields.Str(load_default=None, allow_none=True)


class SubmitAnalysisSchema(Schema):
    """Schema for the POST /experiments/<id>/analysis request body."""

    simulation_path = fields.Str(required=True, validate=validate.Length(min=1))
    analysis = fields.Str(required=True, validate=validate.Length(min=1))
    preprocessing_mode = fields.Str(load_default=PreprocessingMode.AS_IS.value)

    @post_load
    def _convert_enums(self, data: dict, **_kwargs: object) -> dict:
        data["analysis"] = self._to_enum(data["analysis"], AnalysisType, "analysis")
        data["preprocessing_mode"] = self._to_enum(data["preprocessing_mode"], PreprocessingMode, "preprocessing_mode")
        return data

    @staticmethod
    def _to_enum(value: str, enum_cls: type[Enum], field_name: str) -> Enum:
        """Convert a string to an enum member, listing available values on failure."""
        try:
            return enum_cls(value)
        except ValueError:
            available = ", ".join(member.value for member in enum_cls.__members__.values())
            raise ValidationError(f"Unknown {field_name}. Available: {available}", field_name=field_name)
