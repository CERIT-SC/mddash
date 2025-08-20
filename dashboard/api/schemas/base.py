from marshmallow import post_dump
from extensions import ma


class BaseAutoSchema(ma.SQLAlchemyAutoSchema):  # type: ignore
    """Base schema that automatically includes all non-private properties"""
    
    @post_dump(pass_original=True)
    def add_computed_properties(self, data, original_obj, **kwargs):
        """Automatically add all non-private properties"""
        if original_obj:
            for attr_name in dir(original_obj):
                # Skip private attributes and those already in data
                if attr_name.startswith('_') or attr_name in data:
                    continue

                # Skip common object methods we don't want to serialize
                if attr_name in ['metadata', 'query', 'query_class', 'registry']:
                    continue

                try:
                    attr = getattr(type(original_obj), attr_name, None)
                    if isinstance(attr, property):
                        value = getattr(original_obj, attr_name)
                        data[attr_name] = value
                except Exception:
                    # Skip properties that fail to compute
                    pass
        return data
