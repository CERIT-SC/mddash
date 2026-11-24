"""
Make Datahugger populations owned children of a provisional Experiment.

Legacy operations reserved their experiment directory at submission but had no
Experiment row until success. This migration adds measured-progress columns and
a terminal-cancellation state, backfills a provisional Experiment + Notebook
for every orphan operation (reusing the reserved directory ID), and enforces
the one-to-one ownership with a foreign key and unique index.

Revision ID: 016
Revises: 015
Create Date: 2026-11-23
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

_PHASE_VALUES = ("starting", "crawling", "downloading", "finalizing", "cancelling")
_STATUS_OLD = ("queued", "running", "succeeded", "failed")
_STATUS_NEW = ("queued", "running", "cancelling", "succeeded", "failed", "cancelled")

# Server defaults exist only to copy legacy rows into the new NOT NULL columns;
# the models set every value on write, so no DEFAULT remains semantically active.
_PHASE_COLUMN = sa.Column(
    "phase", sa.Enum(*_PHASE_VALUES, name="populationphase"), nullable=False, server_default="starting"
)
_FILES_PRESENT_COLUMN = sa.Column("files_present", sa.Integer, nullable=False, server_default="0")
_FILES_TOTAL_COLUMN = sa.Column("files_total", sa.Integer, nullable=True)
_BYTES_PRESENT_COLUMN = sa.Column("bytes_present", sa.Integer, nullable=False, server_default="0")
_BYTES_TOTAL_COLUMN = sa.Column("bytes_total", sa.Integer, nullable=True)


def _backfill_provisional_experiments(conn: sa.Connection) -> None:
    """
    Create an Experiment + Notebook for every operation that has no parent row.

    A legacy succeeded operation must already own its experiment (finalization
    created it in one transaction); an orphan succeeded row is a data error that
    must be resolved by an operator, not guessed here.
    """
    orphaned = conn.execute(
        sa.text(
            "SELECT po.id, po.experiment_id, po.name, po.repo_url, po.notebooks_repo, "
            "po.module_name, po.module_category, po.engine, po.status, po.created_at, po.updated_at "
            "FROM population_operations po "
            "LEFT JOIN experiments e ON e.id = po.experiment_id "
            "WHERE e.id IS NULL"
        )
    ).all()
    for row in orphaned:
        if row.status == "succeeded":
            raise RuntimeError(
                f"Population operation {row.id} is succeeded but has no experiment row; "
                "resolve manually before upgrading (see migration 016)."
            )
        conn.execute(
            sa.text(
                "INSERT INTO experiments (id, created_at, updated_at, name, module_name, module_category, "
                "source_type, source_ref, notebooks_repo, engine) "
                "VALUES (:id, :created_at, :updated_at, :name, :module_name, :module_category, "
                "'REPO', :repo_url, :notebooks_repo, :engine)"
            ),
            {
                "id": row.experiment_id,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "name": row.name,
                "module_name": row.module_name,
                "module_category": row.module_category,
                "repo_url": row.repo_url,
                "notebooks_repo": row.notebooks_repo,
                "engine": row.engine,
            },
        )
        conn.execute(
            sa.text("INSERT INTO notebooks (experiment_id, token) VALUES (:experiment_id, :token)"),
            {"experiment_id": row.experiment_id, "token": str(uuid.uuid4())},
        )


def upgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("population_operations") as batch_op:
        batch_op.add_column(_PHASE_COLUMN)
        batch_op.add_column(_FILES_PRESENT_COLUMN)
        batch_op.add_column(_FILES_TOTAL_COLUMN)
        batch_op.add_column(_BYTES_PRESENT_COLUMN)
        batch_op.add_column(_BYTES_TOTAL_COLUMN)
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*_STATUS_OLD),
            type_=sa.Enum(*_STATUS_NEW, name="populationstatus"),
            existing_nullable=False,
        )

    # Backfill before the foreign key: every operation must own an experiment row.
    _backfill_provisional_experiments(conn)

    with op.batch_alter_table("population_operations") as batch_op:
        batch_op.create_foreign_key(
            "fk_population_operations_experiment_id_experiments_id",
            "experiments",
            ["experiment_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_population_operations_experiment_id", ["experiment_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("population_operations") as batch_op:
        batch_op.drop_index("ix_population_operations_experiment_id")
        batch_op.drop_constraint("fk_population_operations_experiment_id_experiments_id", type_="foreignkey")

    # Remove the provisional rows the upgrade invented (and nothing else): they own
    # no jobs, so an experiment with children can never match a non-succeeded operation.
    conn.execute(
        sa.text(
            "DELETE FROM notebooks WHERE experiment_id IN ("
            "SELECT po.experiment_id FROM population_operations po WHERE po.status != 'succeeded')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM experiments WHERE id IN ("
            "SELECT po.experiment_id FROM population_operations po WHERE po.status != 'succeeded')"
        )
    )

    with op.batch_alter_table("population_operations") as batch_op:
        batch_op.drop_column("phase")
        batch_op.drop_column("files_present")
        batch_op.drop_column("files_total")
        batch_op.drop_column("bytes_present")
        batch_op.drop_column("bytes_total")
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*_STATUS_NEW, name="populationstatus"),
            type_=sa.Enum(*_STATUS_OLD),
            existing_nullable=False,
        )
