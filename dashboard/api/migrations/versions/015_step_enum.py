"""
Store archive step snapshots as Step names.

The wizard ladder moved from phase ints (Setup 0 .. Analyze 3, publish 4) to
the Step enum. Publish is no longer a step, so 4 lands on ANALYSIS; the
snapshot's archived_status still says published. Names, not values, because
db.Enum stores member names.

Revision ID: 015
Revises: 014
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_STEP = sa.Enum("SETUP", "CONFIGURATION", "SIMULATION", "ANALYSIS", name="step")


def upgrade() -> None:
    # SQLite keeps the text in the INTEGER column until the batch copy retypes it.
    op.execute(
        """
        UPDATE experiments SET archived_step = CASE archived_step
            WHEN 0 THEN 'SETUP'
            WHEN 1 THEN 'CONFIGURATION'
            WHEN 2 THEN 'SIMULATION'
            ELSE 'ANALYSIS'
        END
        WHERE archived_step IS NOT NULL
        """
    )
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.alter_column("archived_step", existing_type=sa.Integer(), type_=_STEP, existing_nullable=True)


def downgrade() -> None:
    op.execute(
        """
        UPDATE experiments SET archived_step = CASE archived_step
            WHEN 'SETUP' THEN 0
            WHEN 'CONFIGURATION' THEN 1
            WHEN 'SIMULATION' THEN 2
            ELSE 3
        END
        WHERE archived_step IS NOT NULL
        """
    )
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.alter_column("archived_step", existing_type=_STEP, type_=sa.Integer(), existing_nullable=True)
