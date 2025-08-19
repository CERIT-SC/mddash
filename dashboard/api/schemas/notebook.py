from flask_marshmallow import Marshmallow

from models import Notebook


ma: Marshmallow = Marshmallow()


class NotebookSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    class Meta:
        model = Notebook
        load_instance = True
        include_fk = True
