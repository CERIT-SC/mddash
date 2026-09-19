"""
Freeze terminal segment progress and enforce one live segment per simulation.

``nsteps_done`` persists a terminal segment's progress (NULL while live) so the
appended multi-segment log can't rewrite history; the partial unique index
(NULL excluded, so legacy never-converged rows don't block the first extend)
makes "one live segment" enforceable under concurrent extends.

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

LIVE_SEGMENTS = sa.text("last_known_status IN ('PENDING', 'RUNNING', 'UNKNOWN')")


def upgrade() -> None:
    with op.batch_alter_table("simulation_jobs") as batch_op:
        batch_op.add_column(sa.Column("nsteps_done", sa.Integer(), nullable=True))

    op.create_index(
        "uq_simulation_jobs_live_segment",
        "simulation_jobs",
        ["experiment_id", "simulation_path"],
        unique=True,
        sqlite_where=LIVE_SEGMENTS,
    )


def downgrade() -> None:
    op.drop_index("uq_simulation_jobs_live_segment", table_name="simulation_jobs")
    with op.batch_alter_table("simulation_jobs") as batch_op:
        batch_op.drop_column("nsteps_done")
