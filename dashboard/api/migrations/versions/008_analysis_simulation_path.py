"""
Add simulation_path to analysis_jobs.

Revision ID: 008
Revises: 007
Create Date: 2026-07-07

Analysis jobs were previously bound only to experiment_id, making it impossible
to cascade-delete them when a simulation is deleted. This adds a non-null
simulation_path column so analysis jobs are properly scoped to their simulation.
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.add_column(sa.Column("simulation_path", sa.String(length=255), nullable=True))

    # Backfill existing rows — there may be none, or they reference unknown simulations.
    op.execute("UPDATE analysis_jobs SET simulation_path = '' WHERE simulation_path IS NULL")

    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.alter_column("simulation_path", existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    """Revert the migration."""
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_column("simulation_path")
