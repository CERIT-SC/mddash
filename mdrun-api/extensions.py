from flask_marshmallow import Marshmallow
from flask_sqlalchemy import SQLAlchemy

db: SQLAlchemy = SQLAlchemy()
ma: Marshmallow = Marshmallow()

__all__ = ["db", "ma"]
