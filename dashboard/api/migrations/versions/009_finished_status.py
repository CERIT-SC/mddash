"""
Rename stored TERMINATED job statuses to FINISHED.

Revision ID: 009
Revises: 008
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

_OLD_VALUES = ("UNKNOWN", "PENDING", "RUNNING", "TERMINATED", "ERROR")
_NEW_VALUES = ("UNKNOWN", "PENDING", "RUNNING", "FINISHED", "ERROR")
# intermediate state that accepts old and new values during data migration
_BOTH_VALUES = (*_OLD_VALUES, "FINISHED")
_TABLES = ("simulation_jobs", "analysis_jobs")


def _set_status_enum(values: tuple[str, ...]) -> None:
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "last_known_status",
                existing_type=sa.Enum(name="jobstatus"),
                type_=sa.Enum(*values, name="jobstatus"),
                existing_nullable=True,
            )


def upgrade() -> None:
    _set_status_enum(_BOTH_VALUES)
    for table in _TABLES:
        op.execute(sa.text(f"UPDATE {table} SET last_known_status='FINISHED' WHERE last_known_status='TERMINATED'"))
    op.execute(
        sa.text(
            "UPDATE tuner_jobs SET preserved_trials = REPLACE(preserved_trials, '\"TERMINATED\"', '\"FINISHED\"')"
            " WHERE preserved_trials LIKE '%TERMINATED%'"
        )
    )
    _set_status_enum(_NEW_VALUES)


def downgrade() -> None:
    _set_status_enum(_BOTH_VALUES)
    for table in _TABLES:
        op.execute(sa.text(f"UPDATE {table} SET last_known_status='TERMINATED' WHERE last_known_status='FINISHED'"))
    op.execute(
        sa.text(
            "UPDATE tuner_jobs SET preserved_trials = REPLACE(preserved_trials, '\"FINISHED\"', '\"TERMINATED\"')"
            " WHERE preserved_trials LIKE '%FINISHED%'"
        )
    )
    _set_status_enum(_OLD_VALUES)
