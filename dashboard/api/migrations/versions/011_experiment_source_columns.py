"""
Replace source_label/source_message display strings with structured source columns.

Backfill parses legacy provenance sentences; unparseable rows keep NULL source
data (the UI hides the source item).

Revision ID: 011
Revises: 010
Create Date: 2026-08-17
"""

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

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
        batch_op.drop_column("source_label")
        batch_op.drop_column("source_message")


def downgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("source_label", sa.String(length=512), nullable=True))
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
