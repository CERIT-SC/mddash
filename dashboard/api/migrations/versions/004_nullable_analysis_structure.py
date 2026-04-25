"""
Make analysis_jobs.structure_file nullable.

Revision ID: 004
Revises: 003
Create Date: 2026-04-24

Analysis jobs may now run with only a topology file (no separate structure file).
mwf accepts topology files as -stru input, and MolStar renders trajectories
using topology-as-structure. This change is required for AMBER analysis support.
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.alter_column(
            "structure_file",
            existing_type=sa.String(255),
            nullable=True,
        )


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.alter_column(
            "structure_file",
            existing_type=sa.String(255),
            nullable=False,
        )
