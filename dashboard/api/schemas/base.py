import functools
import logging
from typing import TYPE_CHECKING, Any

from extensions import ma
from marshmallow import fields, post_dump
from marshmallow_sqlalchemy.convert import ModelConverter

if TYPE_CHECKING:
    from sqlalchemy.types import TypeEngine

logger = logging.getLogger(__name__)


class MDDashModelConverter(ModelConverter):
    """Serialize enum columns by their .value, not .name."""

    def _get_field_class_for_data_type(  # type: ignore
        self,
        data_type: "TypeEngine",
    ) -> type[fields.Field] | functools.partial[type[fields.Field]]:
        result = super()._get_field_class_for_data_type(data_type)
        if isinstance(result, functools.partial) and result.func is fields.Enum:
            keywords = dict(result.keywords, by_value=True)
            return functools.partial(result.func, *result.args, **keywords)
        return result


class BaseAutoSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    """Base schema that automatically includes all non-private properties."""

    class Meta:
        """Metadata for the BaseAutoSchema."""

        model_converter = MDDashModelConverter

    @post_dump
    def remove_private_fields(self, data: dict[str, Any], **kwargs: object) -> dict[str, Any]:  # ruff:ignore[unused-method-argument]
        """
        Remove any fields that start with underscore.

        Returns:
            dict[str, Any]: Serialized data with private fields removed.
        """
        return {key: value for key, value in data.items() if not key.startswith("_")}

    @post_dump(pass_original=True)
    def add_computed_properties(self, data: dict[str, Any], obj: object, **kwargs: object) -> dict[str, Any]:  # ruff:ignore[unused-method-argument]
        """
        Automatically add all non-private properties.

        Returns:
            dict[str, Any]: Serialized data augmented with computed property values.
        """
        if not obj:
            return data

        # Get only properties from the class, not the instance
        obj_type = type(obj)

        for attr_name in dir(obj_type):
            if (
                attr_name.startswith("_")
                or attr_name in data
                or attr_name in {"metadata", "query", "query_class", "registry"}
            ):
                continue

            if isinstance(getattr(obj_type, attr_name, None), property):
                try:
                    data[attr_name] = getattr(obj, attr_name)
                except Exception:
                    logger.warning(f"Failed to compute property '{attr_name}' for {obj_type.__name__}", exc_info=True)

        return data
