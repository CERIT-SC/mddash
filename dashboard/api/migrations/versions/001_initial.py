"""
Initial schema baseline.

Revision ID: 001
Revises: None
Create Date: 2026-03-26

Captures the existing database schema so that Alembic can track future changes.
Existing databases are stamped to this revision without running the upgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(5), primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_message", sa.Text, nullable=False),
        sa.Column("notebooks_repo", sa.String(512), nullable=True),
        sa.Column("mdrepo_id", sa.String(255), nullable=True),
        sa.Column("mdrepo_published", sa.Boolean, nullable=True),
    )

    op.create_table(
        "notebooks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experiment_id", sa.String(5), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("token", sa.String(36), nullable=False),
    )

    op.create_table(
        "gromacs_jobs",
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

    op.create_table(
        "tuner_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(5), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("tpr_name", sa.String(255), nullable=False),
        sa.Column("error_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("is_stopped", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("preserved_trials", sa.JSON, nullable=True),
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(5), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column(
            "analysis_name",
            sa.Enum(
                "pca",
                "rmsds",
                "rgyr",
                "rmsf",
                "fluctuation",
                "dist",
                "energies",
                "hbonds",
                "inter",
                "clusters",
                name="analysistype",
            ),
            nullable=False,
        ),
        sa.Column("structure_file", sa.String(255), nullable=False),
        sa.Column("trajectory_file", sa.String(255), nullable=False),
        sa.Column("topology_file", sa.String(255), nullable=True),
        sa.Column(
            "last_known_status",
            sa.Enum("UNKNOWN", "PENDING", "RUNNING", "TERMINATED", "ERROR", name="jobstatus"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("analysis_jobs")
    op.drop_table("tuner_jobs")
    op.drop_table("gromacs_jobs")
    op.drop_table("notebooks")
    op.drop_table("experiments")
