"""
Freeze terminal segment progress and enforce one live segment per simulation.

Segment history (stop/extend) shows each segment's own step count, but the GMX log
is shared and appended across segments — without a persisted value, an old segment's
``nsteps_done`` re-parses from the newer segment's rows. ``nsteps_done`` lets the
extend flow freeze the display value; NULL while live (parsers fill in).

The partial unique index gives the documented "at most one live segment per
simulation" invariant teeth: an extend creates its row with NULL last_known_status,
so a second concurrent extension of the same simulation inserts a second NULL row
and is rejected instead of spawning two pods that append to one trajectory.
ENUM comparisons use member names (db.Enum convention, cf. 006).

Revision ID: 011
Revises: 010
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

LIVE_SEGMENTS = sa.text("last_known_status IS NULL OR last_known_status IN ('PENDING', 'RUNNING', 'UNKNOWN')")


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
