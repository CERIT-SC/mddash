"""
Add module_name and source_label display fields to experiments, nsteps to tuner_jobs.

Revision ID: 010
Revises: 009
Create Date: 2026-08-13
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

# Frozen copy of clients.tuner.DEFAULT_NSTEPS at migration time; migrations must
# never import live constants — a later default change must not rewrite history.
TUNER_DEFAULT_NSTEPS = 25000


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("module_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("source_label", sa.String(length=512), nullable=True))
    with op.batch_alter_table("tuner_jobs") as batch_op:
        # server_default exists only to backfill rows created before the column did
        batch_op.add_column(sa.Column("nsteps", sa.Integer, nullable=False, server_default=str(TUNER_DEFAULT_NSTEPS)))
    with op.batch_alter_table("tuner_jobs") as batch_op:
        # nsteps is always caller-supplied (fail fast) — no default survives the upgrade
        batch_op.alter_column("nsteps", existing_type=sa.Integer, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("tuner_jobs") as batch_op:
        batch_op.drop_column("nsteps")
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.drop_column("source_label")
        batch_op.drop_column("module_name")
