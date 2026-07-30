"""
Add sim_length_ns column and rename TERMINATED status to FINISHED.

Revision ID: 002
Revises: 001
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("sim_length_ns", sa.Float(), nullable=True))
    op.execute("UPDATE jobs SET status='FINISHED' WHERE status='TERMINATED'")
    op.execute("UPDATE trials SET status='FINISHED' WHERE status='TERMINATED'")


def downgrade() -> None:
    op.execute("UPDATE jobs SET status='TERMINATED' WHERE status='FINISHED'")
    op.execute("UPDATE trials SET status='TERMINATED' WHERE status='FINISHED'")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("sim_length_ns")
