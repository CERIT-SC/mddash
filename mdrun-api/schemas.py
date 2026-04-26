from marshmallow import Schema, fields


class GmxJobCreateRequestSchema(Schema):
    """Schema for validating GROMACS job creation requests."""

    experiment_id = fields.Str(required=True)
    tpr_name = fields.Str(required=True)
    bucket_name = fields.Str(required=True)
    pme = fields.Str(required=True)
    nb = fields.Str(required=True)
    np = fields.Int(required=True)
    ntomp = fields.Int(required=True)
    extra_args = fields.Str(load_default="")


class AmberJobCreateRequestSchema(Schema):
    """Schema for validating AMBER job creation requests."""

    experiment_id = fields.Str(required=True)
    prmtop_name = fields.Str(required=True)
    inpcrd_name = fields.Str(required=True)
    mdin_name = fields.Str(required=True)
    bucket_name = fields.Str(required=True)
    binary = fields.Str(required=True)
    np = fields.Int(required=True)
    ntomp = fields.Int(required=True)
    ewald = fields.Str(required=True)
    extra_args = fields.Str(load_default="")
