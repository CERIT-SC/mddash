"""
Collapse run history to one job row per simulation.

One row per (experiment_id, simulation_path) is now a DB invariant: extend
replaces the row instead of appending segments, and submit replaces a terminal
run. Superseded history rows are deleted (their result files and the appended
log belong to the surviving run; terminal MDRun jobs are owned by the cluster
TTL). The nsteps_done column only existed to freeze history rows, and the
partial live-segment index is replaced by a full unique constraint.

Revision ID: 014
Revises: 013
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the newest row per simulation (created_at, rowid breaks ties).
    op.execute(
        """
        DELETE FROM simulation_jobs
        WHERE EXISTS (
            SELECT 1 FROM simulation_jobs newer
            WHERE newer.experiment_id = simulation_jobs.experiment_id
              AND newer.simulation_path = simulation_jobs.simulation_path
              AND (newer.created_at, newer.rowid) > (simulation_jobs.created_at, simulation_jobs.rowid)
        )
        """
    )
    for child in ("gromacs_jobs", "amber_jobs"):
        op.execute(f"DELETE FROM {child} WHERE id NOT IN (SELECT id FROM simulation_jobs)")

    op.drop_index("uq_simulation_jobs_live_segment", table_name="simulation_jobs")
    with op.batch_alter_table("simulation_jobs") as batch_op:
        batch_op.drop_column("nsteps_done")
        batch_op.create_unique_constraint(
            "uq_simulation_jobs_experiment_simulation", ["experiment_id", "simulation_path"]
        )


def downgrade() -> None:
    with op.batch_alter_table("simulation_jobs") as batch_op:
        batch_op.drop_constraint("uq_simulation_jobs_experiment_simulation", type_="unique")
        batch_op.add_column(sa.Column("nsteps_done", sa.Integer(), nullable=True))
    op.create_index(
        "uq_simulation_jobs_live_segment",
        "simulation_jobs",
        ["experiment_id", "simulation_path"],
        unique=True,
        sqlite_where=sa.text("last_known_status IN ('PENDING', 'RUNNING', 'UNKNOWN')"),
    )
