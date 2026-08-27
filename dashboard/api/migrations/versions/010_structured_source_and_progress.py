"""
Rework experiment display fields and add sim/job progress columns.

Experiments gain module_name and structured source columns (source_type,
source_ref, source_files) replacing the legacy source_message display string.
Backfill parses legacy provenance sentences; unparseable rows keep NULL source
data (the UI hides the source item). Tuner jobs gain a caller-supplied nsteps,
and analysis jobs gain a nullable sim_progress float recording the fraction of
the simulation's steps available when the analysis started, so the UI can flag
results from still-running simulations as partial ("Calculated at N%").

Revision ID: 010
Revises: 009
Create Date: 2026-08-21
"""

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

# Frozen copy of clients.tuner.DEFAULT_NSTEPS at migration time; migrations must
# never import live constants — a later default change must not rewrite history.
TUNER_DEFAULT_NSTEPS = 25000

# Legacy message shapes produced by Experiment.from_pdb / from_repo / from_files.
_PDB_URL_RE = re.compile(r"^Created by downloading PDB file from '([^']+)'\.$")
_OTHER_RE = re.compile(r"^Created by downloading '([^']+)' from RCSB PDB\.$")
_REPO_RE = re.compile(r"^Created by downloading repository from '([^']+)'\.$")
_UPLOAD_RE = re.compile(r"^Created by uploading files: (.+)\.$")


def _parse_source(message: str) -> tuple[str, str | None, str | None] | None:
    """Derive (source_type, source_ref, source_files json) from a legacy source_message."""
    if match := _PDB_URL_RE.match(message):
        return ("pdb", match.group(1), None)
    if match := _OTHER_RE.match(message):
        return ("pdb", match.group(1), None)
    if match := _REPO_RE.match(message):
        return ("repo", match.group(1), None)
    if match := _UPLOAD_RE.match(message):
        return ("file", None, json.dumps(match.group(1).split(", ")))
    return None


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("module_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("source_type", sa.Enum("pdb", "repo", "file", name="sourcetype"), nullable=True))
        batch_op.add_column(sa.Column("source_ref", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("source_files", sa.JSON(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, source_message FROM experiments WHERE source_message IS NOT NULL")
    ).fetchall()
    for experiment_id, message in rows:
        parsed = _parse_source(message)
        if parsed is None:
            continue
        source_type, source_ref, source_files = parsed
        connection.execute(
            sa.text(
                "UPDATE experiments SET source_type = :type, source_ref = :ref, source_files = :files WHERE id = :id"
            ),
            {"type": source_type, "ref": source_ref, "files": source_files, "id": experiment_id},
        )

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
        if source_type == "pdb":
            is_url = bool(source_ref) and source_ref.startswith(("http://", "https://"))
            message = (
                f"Created by downloading PDB file from '{source_ref}'."
                if is_url
                else f"Created by downloading '{source_ref}' from RCSB PDB."
            )
        elif source_type == "repo":
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
