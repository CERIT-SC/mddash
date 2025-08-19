from flask_marshmallow import Marshmallow

from models import GromacsJob


ma = Marshmallow()


class GromacsJobSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    class Meta:
        model = GromacsJob
        load_instance = True
        include_fk = True
