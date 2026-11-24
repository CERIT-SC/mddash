"""
Datahugger-NG population operations.

Revised by 016: the operation is an owned child of a provisional Experiment
that exists from submission, with no terminal pruning.

Revision ID: 015
Revises: 014
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "population_operations",
        sa.Column("id", sa.String(length=16), primary_key=True),
        sa.Column("experiment_id", sa.String(length=5), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repo_url", sa.String(length=512), nullable=False),
        sa.Column("notebooks_repo", sa.String(length=512), nullable=True),
        sa.Column("module_name", sa.String(length=255), nullable=True),
        sa.Column("module_category", sa.String(length=32), nullable=True),
        sa.Column("engine", sa.Enum("GMX", "AMBER"), nullable=False),
        sa.Column("job_name", sa.String(length=63), nullable=False),
        sa.Column("status", sa.Enum("queued", "running", "succeeded", "failed"), nullable=False),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("population_operations")
