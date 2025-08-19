from flask_marshmallow import Marshmallow

from models import TunerJob


ma = Marshmallow()


class TunerJobSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    class Meta:
        model = TunerJob
        load_instance = True
        include_fk = True
