"""
Migrate notebooktier column from value strings to enum names.

Revision ID: 006
Revises: 005
Create Date: 2026-04-28

After commit 2351692 removed values_callable from db.Enum(NotebookTier),
SQLAlchemy stores and validates enum names (SMALL/MEDIUM/LARGE) instead of
values (1x/2x/4x). Existing rows must be updated to match.
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

_VALUE_TO_NAME = {"1x": "SMALL", "2x": "MEDIUM", "4x": "LARGE"}
_NAME_TO_VALUE = {v: k for k, v in _VALUE_TO_NAME.items()}


def upgrade() -> None:
    """Apply the migration."""
    conn = op.get_bind()
    for value, name in _VALUE_TO_NAME.items():
        conn.execute(sa.text("UPDATE notebooks SET tier = :name WHERE tier = :value"), {"name": name, "value": value})

    with op.batch_alter_table("notebooks") as batch_op:
        batch_op.alter_column(
            "tier",
            existing_type=sa.Enum("1x", "2x", "4x", name="notebooktier"),
            type_=sa.Enum("SMALL", "MEDIUM", "LARGE", name="notebooktier"),
            nullable=True,
        )


def downgrade() -> None:
    """Revert the migration."""
    conn = op.get_bind()
    for name, value in _NAME_TO_VALUE.items():
        conn.execute(sa.text("UPDATE notebooks SET tier = :value WHERE tier = :name"), {"name": name, "value": value})

    with op.batch_alter_table("notebooks") as batch_op:
        batch_op.alter_column(
            "tier",
            existing_type=sa.Enum("SMALL", "MEDIUM", "LARGE", name="notebooktier"),
            type_=sa.Enum("1x", "2x", "4x", name="notebooktier"),
            nullable=True,
        )
