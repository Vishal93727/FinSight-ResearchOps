"""Pin benchmark snapshots and persist deterministic experiment risk reviews.

Revision ID: 0004_phase2_benchmark_risk_review
Revises: 0003_experiment_run_idempotency
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_phase2_benchmark_risk_review"
down_revision = "0003_experiment_run_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite supports REFERENCES in a raw ADD COLUMN statement, but Alembic's
        # add_column(ForeignKey) emits a separate ALTER CONSTRAINT which SQLite lacks.
        op.execute(
            "ALTER TABLE experiments ADD COLUMN benchmark_snapshot_id VARCHAR(36) "
            "REFERENCES data_snapshots(id) ON DELETE RESTRICT"
        )
    else:
        op.add_column("experiments", sa.Column("benchmark_snapshot_id", sa.String(length=36), nullable=True))
        op.create_foreign_key(
            "fk_experiments_benchmark_snapshot_id_data_snapshots",
            "experiments", "data_snapshots", ["benchmark_snapshot_id"], ["id"], ondelete="RESTRICT",
        )
    op.create_index("ix_experiments_benchmark_snapshot_id", "experiments", ["benchmark_snapshot_id"], unique=False)
    op.create_table(
        "experiment_risk_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("observed_metrics", sa.JSON(), nullable=False),
        sa.Column("breaches", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("override_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_experiment_risk_review_run"),
    )
    op.create_index("ix_experiment_risk_reviews_run_id", "experiment_risk_reviews", ["run_id"], unique=False)
    op.create_index("ix_experiment_risk_reviews_decision", "experiment_risk_reviews", ["decision"], unique=False)
    op.create_index("ix_risk_review_decision_created", "experiment_risk_reviews", ["decision", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_review_decision_created", table_name="experiment_risk_reviews")
    op.drop_index("ix_experiment_risk_reviews_decision", table_name="experiment_risk_reviews")
    op.drop_index("ix_experiment_risk_reviews_run_id", table_name="experiment_risk_reviews")
    op.drop_table("experiment_risk_reviews")
    op.drop_index("ix_experiments_benchmark_snapshot_id", table_name="experiments")
    if op.get_bind().dialect.name == "sqlite":
        op.drop_column("experiments", "benchmark_snapshot_id")
    else:
        op.drop_constraint("fk_experiments_benchmark_snapshot_id_data_snapshots", "experiments", type_="foreignkey")
        op.drop_column("experiments", "benchmark_snapshot_id")
