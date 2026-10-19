"""Shared schema building blocks. Class names are the OpenAPI component names the UI client is generated from."""

import logging
from enum import Enum
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator, with_config

logger = logging.getLogger(__name__)


def enum_schema(enum_cls: type[Enum], *, nullable: bool = False) -> dict:
    """Inline JSON schema of an enum's values (no component: generated clients name it after the field)."""
    values: list[object] = [member.value for member in enum_cls]
    if nullable:
        return {"type": ["string", "null"], "enum": [*values, None]}
    return {"type": "string", "enum": values}


class _LenientAttributes:
    """Attribute view where a failing property reads as absent (optional fields fall back to their default)."""

    def __init__(self, obj: object) -> None:
        self._obj = obj

    def __getattr__(self, name: str) -> Any:  # ruff:ignore[any-type]
        try:
            return getattr(self._obj, name)
        except Exception as e:
            # Derived values parse files that may be gone (e.g. a deleted manifest); one bad
            # property must not fail the whole payload.
            logger.warning("Failed to compute '%s' for %s", name, type(self._obj).__name__, exc_info=True)
            raise AttributeError(name) from e


class OrmModel(BaseModel):
    """Response model read from ORM attributes and properties."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _lenient(cls, data: Any) -> Any:  # ruff:ignore[any-type]
        if isinstance(data, (dict, BaseModel, _LenientAttributes)):
            return data
        return _LenientAttributes(data)


@with_config(ConfigDict(extra="forbid"))
class Problem(TypedDict):
    """RFC 9457 problem details. The HTTP status is carried by the response status line."""

    type: Annotated[str, Field(pattern=r"^urn:mddash:", json_schema_extra={"format": "uri"})]
    title: Annotated[str, Field(min_length=1)]
    detail: Annotated[str, Field(min_length=1)]
    solution: NotRequired[Annotated[str, Field(min_length=1)]]


@with_config(ConfigDict(extra="forbid"))
class Message(TypedDict):
    """Plain confirmation message."""

    message: str


@with_config(ConfigDict(extra="forbid"))
class FileInfo(TypedDict):
    """A file inside an experiment directory with its download URL."""

    name: str
    size: Annotated[int, Field(ge=0)]
    path: str
    url: str


ArchiveState = Literal["archiving", "archived", "restoring", "archive_failed", "restore_failed"]
