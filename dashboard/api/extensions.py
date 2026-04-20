from enum import Enum

from flask_marshmallow import Marshmallow
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


def enum_values(enum_class: type[Enum]) -> list[str]:
    """
    Extract .value from each member — use when enum values differ from names.

    Returns:
        list[str]: The values of all enum members.
    """
    return [m.value for m in enum_class]


# Singletons
db: SQLAlchemy = SQLAlchemy()
ma: Marshmallow = Marshmallow()
migrate: Migrate = Migrate()

__all__ = ["db", "ma", "migrate"]
