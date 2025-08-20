from models import GromacsJob
from extensions import ma


class GromacsJobSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    class Meta:
        model = GromacsJob
        load_instance = True
        include_fk = True
