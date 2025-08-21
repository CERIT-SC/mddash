from models import GromacsJob
from .base import BaseAutoSchema


class GromacsJobSchema(BaseAutoSchema):
    class Meta:
        model = GromacsJob
        load_instance = True
        include_fk = True
