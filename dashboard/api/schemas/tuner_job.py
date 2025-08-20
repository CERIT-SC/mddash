from models import TunerJob
from .base import BaseAutoSchema


class TunerJobSchema(BaseAutoSchema):
    class Meta:
        model = TunerJob
        load_instance = True
        include_fk = True
