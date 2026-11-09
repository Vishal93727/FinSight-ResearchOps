"""Phase 5 realised outcome, drift and research suggestion ledgers."""
from alembic import op
import sqlalchemy as sa

revision = "0008_phase5_feedback_monitoring"
down_revision = "0007_phase4_governance_rl_paper_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_symbol", sa.String(32), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("realised_date", sa.Date(), nullable=False),
        sa.Column("horizon_sessions", sa.Integer(), nullable=False),
        sa.Column("predicted_return", sa.Float(), nullable=False),
        sa.Column("realised_return", sa.Float(), nullable=False),
        sa.Column("benchmark_return", sa.Float()),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="SET NULL")),
        sa.Column("experiment_run_id", sa.String(36), sa.ForeignKey("experiment_runs.id", ondelete="SET NULL")),
        sa.Column("paper_account_id", sa.String(36), sa.ForeignKey("paper_accounts.id", ondelete="SET NULL")),
        sa.Column("observation_source", sa.String(80), nullable=False),
        sa.Column("source_reference", sa.String(500)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ("instrument_symbol", "forecast_date", "realised_date", "model_version_id", "experiment_run_id", "paper_account_id", "created_by", "created_at"):
        op.create_index(f"ix_prediction_outcomes_{col}", "prediction_outcomes", [col])
    op.create_index("ix_prediction_outcomes_model_realised", "prediction_outcomes", ["model_version_id", "realised_date"])

    op.create_table(
        "drift_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="SET NULL")),
        sa.Column("reference_snapshot_id", sa.String(36), sa.ForeignKey("data_snapshots.id", ondelete="SET NULL")),
        sa.Column("current_snapshot_id", sa.String(36), sa.ForeignKey("data_snapshots.id", ondelete="SET NULL")),
        sa.Column("overall_status", sa.String(16), nullable=False),
        sa.Column("feature_results", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ("model_version_id", "overall_status", "created_by", "created_at"):
        op.create_index(f"ix_drift_assessments_{col}", "drift_assessments", [col])

    op.create_table(
        "research_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decision_comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    for col in ("status", "created_by", "created_at"):
        op.create_index(f"ix_research_suggestions_{col}", "research_suggestions", [col])


def downgrade() -> None:
    op.drop_table("research_suggestions")
    op.drop_table("drift_assessments")
    op.drop_table("prediction_outcomes")
