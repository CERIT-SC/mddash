"""
Add engine column to jobs table.

Revision ID: 001
Revises:
Create Date: 2026-04-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = "000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("engine", sa.String(), nullable=False, server_default="gmx"))
        batch_op.create_index("ix_jobs_engine", ["engine"])


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_engine")
        batch_op.drop_column("engine")
