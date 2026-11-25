"""
Datahugger-NG population operations.

Each operation is an owned child of a provisional Experiment that exists from submission.

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
        sa.Column(
            "experiment_id",
            sa.String(length=5),
            sa.ForeignKey(
                "experiments.id", name="fk_population_operations_experiment_id_experiments_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repo_url", sa.String(length=512), nullable=False),
        sa.Column("notebooks_repo", sa.String(length=512), nullable=True),
        sa.Column("module_name", sa.String(length=255), nullable=True),
        sa.Column("module_category", sa.String(length=32), nullable=True),
        sa.Column("engine", sa.Enum("GMX", "AMBER"), nullable=False),
        sa.Column("job_name", sa.String(length=63), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "cancelling", "succeeded", "failed", "cancelled", name="populationstatus"),
            nullable=False,
        ),
        sa.Column(
            "phase",
            sa.Enum("starting", "crawling", "downloading", "finalizing", "cancelling", name="populationphase"),
            nullable=False,
        ),
        sa.Column("files_present", sa.Integer, nullable=False),
        sa.Column("files_total", sa.Integer, nullable=True),
        sa.Column("bytes_present", sa.Integer, nullable=False),
        sa.Column("bytes_total", sa.Integer, nullable=True),
        sa.Column("renamed_paths", sa.JSON, nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_population_operations_experiment_id", "population_operations", ["experiment_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_population_operations_experiment_id", table_name="population_operations")
    op.drop_table("population_operations")
