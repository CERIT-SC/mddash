"""
Add module_category: creation snapshot of the curated module's category.

Existing rows backfill by (module_name, engine) — the engine disambiguates
curated names repeated across engines; custom and unknown keep NULL.

Revision ID: 011
Revises: 010
Create Date: 2026-09-15
"""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

# Read the catalog JSON directly — migrations never import live code (cf. 010).
_CATALOG_PATH = Path(__file__).resolve().parents[2] / "notebook-modules.json"


def upgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.add_column(sa.Column("module_category", sa.String(length=32), nullable=True))

    connection = op.get_bind()
    for module in json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))["modules"]:
        connection.execute(
            sa.text(
                "UPDATE experiments SET module_category = :category "
                "WHERE module_name = :name AND engine = :engine AND module_category IS NULL"
            ),
            {"category": module["category"], "name": module["name"], "engine": module["engine"]},
        )


def downgrade() -> None:
    with op.batch_alter_table("experiments") as batch_op:
        batch_op.drop_column("module_category")
