"""Add idempotency key support to experiment run submission.

Revision ID: 0003_experiment_run_idempotency
Revises: 0002_research_experiment_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_experiment_run_idempotency"
down_revision = "0002_research_experiment_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiment_runs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index("uq_experiment_run_idempotency", "experiment_runs", ["experiment_id", "idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_experiment_run_idempotency", table_name="experiment_runs")
    op.drop_column("experiment_runs", "idempotency_key")
