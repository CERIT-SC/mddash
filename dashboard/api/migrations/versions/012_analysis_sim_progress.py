"""
Add sim_progress to analysis_jobs.

Revision ID: 012
Revises: 011
Create Date: 2026-08-21

An analysis run against a still-running simulation only covers the trajectory
snapshot taken when its job started. This nullable float column records the
fraction of the simulation's steps available at that moment so the UI can flag
results as partial ("Calculated at N%") instead of presenting them as complete.
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.add_column(sa.Column("sim_progress", sa.Float(), nullable=True))


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_column("sim_progress")
