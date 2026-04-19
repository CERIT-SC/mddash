"""
Joined Table Inheritance for simulation jobs and AMBER engine support.

Revision ID: 003
Revises: 002
Create Date: 2026-04-15

Restructures simulation jobs to use Joined Table Inheritance (JTI):
- Creates simulation_jobs base table with shared columns
- Migrates existing gromacs_jobs data to simulation_jobs
- Rebuilds gromacs_jobs as a child table with FK to simulation_jobs
- Creates amber_jobs child table for AMBER simulations
- Adds engine column to experiments
- Adds AMBER-specific columns to tuner_jobs
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    # Step 1: Create simulation_jobs table (base table for JTI)
    op.create_table(
        "simulation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(5), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("engine", sa.Enum("gmx", "amber", name="engine"), nullable=False, server_default="gmx"),
        sa.Column("np", sa.Integer, nullable=False),
        sa.Column("ntomp", sa.Integer, nullable=False),
        sa.Column("extra_args", sa.Text, nullable=True, server_default=""),
        sa.Column("start_timestamp", sa.Integer, nullable=True),
        sa.Column("finish_timestamp", sa.Integer, nullable=True),
        sa.Column("nsteps", sa.Integer, nullable=True),
        sa.Column("performance", sa.Float, nullable=True),
        sa.Column(
            "last_known_status",
            sa.Enum("UNKNOWN", "PENDING", "RUNNING", "TERMINATED", "ERROR", name="jobstatus"),
            nullable=True,
        ),
    )

    # Step 2: Populate simulation_jobs from existing gromacs_jobs
    op.execute(
        """
        INSERT INTO simulation_jobs (
            id, experiment_id, created_at, engine, np, ntomp, extra_args,
            start_timestamp, finish_timestamp, nsteps, performance, last_known_status
        )
        SELECT
            id, experiment_id, created_at, 'gmx', np, ntomp, extra_args,
            start_timestamp, finish_timestamp, nsteps, performance, last_known_status
        FROM gromacs_jobs
        """
    )

    # Step 3: Rebuild gromacs_jobs as a child table
    # SQLite requires recreating the table to change the PK to a FK
    # Create new table with correct schema
    op.create_table(
        "gromacs_jobs_new",
        sa.Column("id", sa.String(36), sa.ForeignKey("simulation_jobs.id"), primary_key=True),
        sa.Column("tpr_name", sa.String(255), nullable=False),
        sa.Column("pme", sa.Enum("auto", "cpu", "gpu", name="devicetype"), nullable=False),
        sa.Column("nb", sa.Enum("auto", "cpu", "gpu", name="devicetype"), nullable=False),
    )

    # Copy data from old gromacs_jobs to new table
    op.execute(
        """
        INSERT INTO gromacs_jobs_new (id, tpr_name, pme, nb)
        SELECT id, tpr_name, pme, nb FROM gromacs_jobs
        """
    )

    # Drop old table and rename new table
    op.drop_table("gromacs_jobs")
    op.rename_table("gromacs_jobs_new", "gromacs_jobs")

    # Step 4: Create amber_jobs table (child table for AMBER simulations)
    op.create_table(
        "amber_jobs",
        sa.Column("id", sa.String(36), sa.ForeignKey("simulation_jobs.id"), primary_key=True),
        sa.Column("prmtop_name", sa.String(255), nullable=False),
        sa.Column("inpcrd_name", sa.String(255), nullable=False),
        sa.Column("mdin_name", sa.String(255), nullable=False),
        sa.Column("binary", sa.Enum("pmemd.cuda", "pmemd.MPI", name="amberbinary"), nullable=False),
        sa.Column("ewald", sa.Enum("default", "optimized", name="ewaldpreset"), nullable=False),
    )

    # Step 5: Add engine column to experiments
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(
            sa.Column("engine", sa.Enum("gmx", "amber", name="engine"), nullable=False, server_default="gmx")
        )

    # Step 6: Add AMBER columns to tuner_jobs
    with op.batch_alter_table("tuner_jobs") as batch_op:
        batch_op.add_column(sa.Column("inpcrd_name", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("mdin_name", sa.String(255), nullable=True))


def downgrade() -> None:
    """Revert the migration."""
    # Step 6: Remove AMBER columns from tuner_jobs
    with op.batch_alter_table("tuner_jobs") as batch_op:
        batch_op.drop_column("mdin_name")
        batch_op.drop_column("inpcrd_name")

    # Step 5: Remove engine column from experiments
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.drop_column("engine")

    # Step 4: Drop amber_jobs table
    op.drop_table("amber_jobs")

    # Step 3: Restore original gromacs_jobs schema
    # Create table with original schema
    op.create_table(
        "gromacs_jobs_new",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(5), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("tpr_name", sa.String(255), nullable=False),
        sa.Column("pme", sa.Enum("auto", "cpu", "gpu", name="devicetype"), nullable=False),
        sa.Column("nb", sa.Enum("auto", "cpu", "gpu", name="devicetype"), nullable=False),
        sa.Column("np", sa.Integer, nullable=False),
        sa.Column("ntomp", sa.Integer, nullable=False),
        sa.Column("extra_args", sa.Text, nullable=True),
        sa.Column("start_timestamp", sa.Integer, nullable=True),
        sa.Column("finish_timestamp", sa.Integer, nullable=True),
        sa.Column("nsteps", sa.Integer, nullable=True),
        sa.Column("performance", sa.Float, nullable=True),
        sa.Column(
            "last_known_status",
            sa.Enum("UNKNOWN", "PENDING", "RUNNING", "TERMINATED", "ERROR", name="jobstatus"),
            nullable=True,
        ),
    )

    # Copy data back from simulation_jobs and gromacs_jobs
    op.execute(
        """
        INSERT INTO gromacs_jobs_new (
            id, experiment_id, created_at, tpr_name, pme, nb, np, ntomp, extra_args,
            start_timestamp, finish_timestamp, nsteps, performance, last_known_status
        )
        SELECT
            sj.id, sj.experiment_id, sj.created_at, gj.tpr_name, gj.pme, gj.nb,
            sj.np, sj.ntomp, sj.extra_args,
            sj.start_timestamp, sj.finish_timestamp, sj.nsteps, sj.performance, sj.last_known_status
        FROM simulation_jobs sj
        JOIN gromacs_jobs gj ON sj.id = gj.id
        """
    )

    # Drop current gromacs_jobs and rename
    op.drop_table("gromacs_jobs")
    op.rename_table("gromacs_jobs_new", "gromacs_jobs")

    # Step 2: Clear migrated data (nothing to do - Step 1 handles the table)

    # Step 1: Drop simulation_jobs table
    op.drop_table("simulation_jobs")
