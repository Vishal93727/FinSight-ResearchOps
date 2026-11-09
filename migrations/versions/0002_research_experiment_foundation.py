"""Research hypotheses, feature-set versions and reproducible experiment specifications.

Revision ID: 0002_research_experiment_foundation
Revises: 0001_initial_researchops

This revision is intentionally explicit: historical migrations must not change when
current SQLAlchemy models evolve in later releases.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_research_experiment_foundation"
down_revision = "0001_initial_researchops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_hypotheses",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_hypotheses_symbol", "research_hypotheses", ["symbol"])
    op.create_index("ix_research_hypotheses_status", "research_hypotheses", ["status"])
    op.create_index("ix_research_hypotheses_owner_user_id", "research_hypotheses", ["owner_user_id"])
    op.create_index("ix_hypothesis_symbol_status", "research_hypotheses", ["symbol", "status"])

    op.create_table(
        "feature_set_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("feature_key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), nullable=False),
        sa.Column("definition_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["data_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_key", "version", name="uq_feature_key_version"),
    )
    op.create_index("ix_feature_set_versions_feature_key", "feature_set_versions", ["feature_key"])
    op.create_index("ix_feature_set_versions_source_snapshot_id", "feature_set_versions", ["source_snapshot_id"])
    op.create_index("ix_feature_set_versions_definition_sha256", "feature_set_versions", ["definition_sha256"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("hypothesis_id", sa.String(36), nullable=False),
        sa.Column("instrument_symbol", sa.String(32), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(36), nullable=False),
        sa.Column("feature_set_version_id", sa.String(36), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("configuration_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["research_hypotheses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["data_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["feature_set_version_id"], ["feature_set_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiments_hypothesis_id", "experiments", ["hypothesis_id"])
    op.create_index("ix_experiments_instrument_symbol", "experiments", ["instrument_symbol"])
    op.create_index("ix_experiments_dataset_snapshot_id", "experiments", ["dataset_snapshot_id"])
    op.create_index("ix_experiments_feature_set_version_id", "experiments", ["feature_set_version_id"])
    op.create_index("ix_experiments_configuration_sha256", "experiments", ["configuration_sha256"])
    op.create_index("ix_experiments_status", "experiments", ["status"])
    op.create_index("ix_experiment_symbol_status", "experiments", ["instrument_symbol", "status"])

    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "run_number", name="uq_experiment_run_number"),
    )
    op.create_index("ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"])
    op.create_index("ix_experiment_runs_status", "experiment_runs", ["status"])


def downgrade() -> None:
    op.drop_table("experiment_runs")
    op.drop_table("experiments")
    op.drop_table("feature_set_versions")
    op.drop_table("research_hypotheses")
