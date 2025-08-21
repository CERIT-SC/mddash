"""Shared Flask extensions.

Keep singletons here and import in app/models/routes to avoid multiple
independent SQLAlchemy/Marshmallow instances.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow

# Singletons
db: SQLAlchemy = SQLAlchemy()
ma: Marshmallow = Marshmallow()

__all__ = ["db", "ma"]
