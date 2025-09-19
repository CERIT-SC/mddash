from marshmallow import Schema, fields


class JobCreateRequestSchema(Schema):
    experiment_id = fields.Str(required=True)
    tpr_name = fields.Str(required=True)
    bucket_name = fields.Str(required=True)
    pme = fields.Str(required=True)
    nb = fields.Str(required=True)
    np = fields.Int(required=True)
    ntomp = fields.Int(required=True)
    extra_args = fields.Str(load_default='')
