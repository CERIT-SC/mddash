"""
Add notebook resource tier and GPU columns.

Revision ID: 002
Revises: 001
Create Date: 2026-03-26

Adds tier (enum: 1x, 2x, 4x) and gpu (boolean) columns to the notebooks table
so users can select resource sizes when starting a notebook.
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notebooks") as batch_op:
        batch_op.add_column(sa.Column("tier", sa.Enum("1x", "2x", "4x", name="notebooktier"), nullable=True))
        batch_op.add_column(sa.Column("gpu", sa.Boolean(), server_default=sa.text("0"), nullable=False))


def downgrade():
    with op.batch_alter_table("notebooks") as batch_op:
        batch_op.drop_column("gpu")
        batch_op.drop_column("tier")
