from models import Notebook
from .base import BaseAutoSchema


class NotebookSchema(BaseAutoSchema):
    class Meta:
        model = Notebook
        load_instance = True
        include_fk = True
