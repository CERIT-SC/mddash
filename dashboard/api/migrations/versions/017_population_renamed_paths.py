"""
Record dataset entries renamed when a Datahugger merge meets a name the notebooks already use.

Revision ID: 017
Revises: 016
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("population_operations") as batch:
        batch.add_column(sa.Column("renamed_paths", sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("population_operations") as batch:
        batch.drop_column("renamed_paths")
