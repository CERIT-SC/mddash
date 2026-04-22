from flask_marshmallow import Marshmallow
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Singletons
db: SQLAlchemy = SQLAlchemy()
ma: Marshmallow = Marshmallow()
migrate: Migrate = Migrate()

__all__ = ["db", "ma", "migrate"]
