"""
Add init_step column to gromacs_jobs.

Revision ID: 005
Revises: 004
Create Date: 2026-04-26

Tracks the starting step when a GROMACS simulation resumes from a checkpoint.
Required for accurate ETA calculation — without it, elapsed time is divided by
the absolute step count instead of steps completed in the current run.
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("gromacs_jobs") as batch_op:
        batch_op.add_column(sa.Column("init_step", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("gromacs_jobs") as batch_op:
        batch_op.drop_column("init_step")
