from models import Experiment
from extensions import ma


class ExperimentSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    class Meta:
        model = Experiment
        load_instance = True
        include_relationships = True
