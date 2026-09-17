"""
Add archive snapshot columns to experiments.

Revision ID: 012
Revises: 011
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("archived_size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("archived_step", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("archived_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.drop_column("archived_at")
        batch_op.drop_column("archived_size_bytes")
        batch_op.drop_column("archived_step")
        batch_op.drop_column("archived_status")
