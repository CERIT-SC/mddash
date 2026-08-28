"""
Rework experiment display fields and add sim/job progress columns.

Experiments gain module_name and structured source columns (source_type,
source_ref, source_files) replacing the legacy source_message display string.
Legacy rows are not backfilled — free-text provenance can't be safely mapped
into enum names (db.Enum convention, cf. 006) — so they keep NULL source data
(the UI hides the source item). Tuner jobs gain a caller-supplied nsteps, and
analysis jobs gain a nullable sim_progress float recording the fraction of the
simulation's steps available when the analysis started, so the UI can flag
results from still-running simulations as partial ("Calculated at N%").

Revision ID: 010
Revises: 009
Create Date: 2026-08-21
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

# Frozen copy of clients.tuner.DEFAULT_NSTEPS at migration time; migrations must
# never import live constants — a later default change must not rewrite history.
TUNER_DEFAULT_NSTEPS = 25000


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("module_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("source_type", sa.Enum("PDB", "REPO", "FILE", name="sourcetype"), nullable=True))
        batch_op.add_column(sa.Column("source_ref", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("source_files", sa.JSON(), nullable=True))

    with op.batch_alter_table("experiments") as batch_op:
        batch_op.drop_column("source_message")
    with op.batch_alter_table("tuner_jobs") as batch_op:
        # server_default exists only to backfill rows created before the column did
        batch_op.add_column(sa.Column("nsteps", sa.Integer, nullable=False, server_default=str(TUNER_DEFAULT_NSTEPS)))
    with op.batch_alter_table("tuner_jobs") as batch_op:
        # nsteps is always caller-supplied (fail fast) — no default survives the upgrade
        batch_op.alter_column("nsteps", existing_type=sa.Integer, server_default=None)
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.add_column(sa.Column("sim_progress", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_column("sim_progress")
    with op.batch_alter_table("tuner_jobs") as batch_op:
        batch_op.drop_column("nsteps")

    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("source_message", sa.Text(), nullable=False, server_default=""))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, source_type, source_ref, source_files FROM experiments WHERE source_type IS NOT NULL")
    ).fetchall()
    for experiment_id, source_type, source_ref, source_files in rows:
        if source_type == "PDB":
            is_url = bool(source_ref) and source_ref.startswith(("http://", "https://"))
            message = (
                f"Created by downloading PDB file from '{source_ref}'."
                if is_url
                else f"Created by downloading '{source_ref}' from RCSB PDB."
            )
        elif source_type == "REPO":
            message = f"Created by downloading repository from '{source_ref}'."
        else:
            uploaded = json.loads(source_files) if source_files else []
            message = f"Created by uploading files: {', '.join(uploaded)}."
        connection.execute(
            sa.text("UPDATE experiments SET source_message = :message WHERE id = :id"),
            {"message": message, "id": experiment_id},
        )

    with op.batch_alter_table("experiments") as batch_op:
        batch_op.alter_column("source_message", existing_type=sa.Text(), server_default=None)
        batch_op.drop_column("source_type")
        batch_op.drop_column("source_ref")
        batch_op.drop_column("source_files")
        batch_op.drop_column("module_name")
