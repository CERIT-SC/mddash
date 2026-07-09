"""
Simulation manifest as source of truth.

Revision ID: 007
Revises: 006
Create Date: 2026-07-01

DESTRUCTIVE: purges all existing tuner/simulation jobs before dropping the old
engine-specific file columns and extra_args. Job data is NOT restored on
downgrade. Adds non-null simulation_path to tuner_jobs and simulation_jobs as
the new job identity.
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Apply the destructive simulation-source-of-truth migration.

    WARNING: Purges all existing tuner/simulation/amber/gromacs jobs. In-flight
    K8s/tuner jobs are NOT cleaned up (their DB records are deleted). Ensure no
    running jobs exist at deploy time, or manually `kubectl delete job` them.
    """
    conn = op.get_bind()

    # Purge existing job rows before schema changes (constraints: child tables first).
    conn.execute(sa.text("DELETE FROM amber_jobs"))
    conn.execute(sa.text("DELETE FROM gromacs_jobs"))
    conn.execute(sa.text("DELETE FROM simulation_jobs"))
    conn.execute(sa.text("DELETE FROM tuner_jobs"))

    # simulation_jobs: add simulation_path, drop extra_args.
    with op.batch_alter_table("simulation_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("simulation_path", sa.String(length=255), nullable=True))
        batch_op.drop_column("extra_args")

    conn.execute(sa.text("UPDATE simulation_jobs SET simulation_path = '' WHERE simulation_path IS NULL"))

    with op.batch_alter_table("simulation_jobs", schema=None) as batch_op:
        batch_op.alter_column("simulation_path", existing_type=sa.String(length=255), nullable=False)

    # tuner_jobs: add simulation_path, drop engine-specific file columns.
    with op.batch_alter_table("tuner_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("simulation_path", sa.String(length=255), nullable=True))
        batch_op.drop_column("tpr_name")
        batch_op.drop_column("inpcrd_name")
        batch_op.drop_column("mdin_name")

    conn.execute(sa.text("UPDATE tuner_jobs SET simulation_path = '' WHERE simulation_path IS NULL"))

    with op.batch_alter_table("tuner_jobs", schema=None) as batch_op:
        batch_op.alter_column("simulation_path", existing_type=sa.String(length=255), nullable=False)

    # gromacs_jobs: drop tpr_name.
    with op.batch_alter_table("gromacs_jobs", schema=None) as batch_op:
        batch_op.drop_column("tpr_name")

    # amber_jobs: drop prmtop_name, inpcrd_name, mdin_name.
    with op.batch_alter_table("amber_jobs", schema=None) as batch_op:
        batch_op.drop_column("prmtop_name")
        batch_op.drop_column("inpcrd_name")
        batch_op.drop_column("mdin_name")


def downgrade() -> None:
    """Recreate dropped columns without restoring purged job data."""
    # Recreate dropped columns (nullable/defaulted). Purged job data is NOT restored.
    with op.batch_alter_table("amber_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prmtop_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("inpcrd_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("mdin_name", sa.String(length=255), nullable=True))

    with op.batch_alter_table("gromacs_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tpr_name", sa.String(length=255), nullable=True))

    with op.batch_alter_table("tuner_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tpr_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("inpcrd_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("mdin_name", sa.String(length=255), nullable=True))
        batch_op.drop_column("simulation_path")

    with op.batch_alter_table("simulation_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extra_args", sa.Text(), nullable=True))
        batch_op.drop_column("simulation_path")
